import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

from app.desktop.git_sync.config import get_git_sync_config, project_path_from_id
from app.desktop.git_sync.errors import (
    CorruptRepoError,
    GitSyncError,
    RemoteUnreachableError,
    SyncConflictError,
    WriteLockTimeoutError,
)
from app.desktop.git_sync.git_sync_manager import GitSyncManager
from app.desktop.git_sync.registry import GitSyncRegistry

logger = logging.getLogger(__name__)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

PROJECT_ID_PATTERN = re.compile(r"^/api/projects/([^/]+)")

LONG_LOCK_HOLD_THRESHOLD = 5.0


def _is_dev_mode() -> bool:
    return os.environ.get("KILN_DEV_MODE", "false") == "true"


class _StreamingUnderWriteLock(Exception):
    """Sentinel raised when an SSE response is detected under the write lock.

    Raising inside an atomic_write block triggers rollback of any dirty
    changes. The middleware catches this sentinel just outside the block
    and returns a 500 JSON response.
    """


ERROR_MAP: dict[type[GitSyncError], tuple[int, str]] = {
    RemoteUnreachableError: (
        503,
        "Cannot sync with remote. Check your connection.",
    ),
    SyncConflictError: (
        409,
        "There was a problem saving. Please try again.",
    ),
    WriteLockTimeoutError: (
        503,
        "Another save is in progress. Please wait a moment and try again.",
    ),
    CorruptRepoError: (
        500,
        "Git repository is in an unexpected state.",
    ),
}


class GitSyncMiddleware(BaseHTTPMiddleware):
    """Wraps mutating requests with write lock + git commit/push.

    For non-mutating requests and non-auto-sync routes,
    passes through without buffering (preserves streaming responses).
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        manager = self._get_manager_for_request(request)

        if manager is None:
            return await self._unmatched_dispatch(request, call_next)

        endpoint = self._resolve_endpoint(request)
        needs_lock = (
            request.method in MUTATING_METHODS
            or getattr(endpoint, "_git_sync_write_lock", False)
        ) and not getattr(endpoint, "_git_sync_no_write_lock", False)

        if not needs_lock:
            # Expose the manager so @no_write_lock endpoints can build a
            # SaveContext without importing desktop-layer code.
            request.state.git_sync_manager = manager
            try:
                await manager.ensure_fresh_for_read()
            except GitSyncError as e:
                status, message = self._map_error(e)
                return Response(
                    content=json.dumps({"detail": message}, ensure_ascii=False),
                    status_code=status,
                    media_type="application/json",
                )
            self._notify_background_sync(manager)

            # @no_write_lock endpoints manage their own atomic_write blocks
            # per job, so a dirty check here would race in-flight commits.
            # Skip them entirely, per the functional spec.
            is_self_managed = getattr(endpoint, "_git_sync_no_write_lock", False)
            if is_self_managed:
                return await call_next(request)

            response = await call_next(request)

            if _is_dev_mode():
                return await self._dev_mode_dirty_check(request, response, manager)

            return response

        self._notify_background_sync(manager)
        lock_start = time.monotonic()
        try:
            async with manager.atomic_write(f"{request.method} {request.url.path}"):
                response = await call_next(request)

                content_type = response.headers.get("content-type", "")
                if "text/event-stream" in content_type:
                    logger.error(
                        "Streaming response under write lock for %s %s -- "
                        "use @no_write_lock instead",
                        request.method,
                        request.url.path,
                    )
                    raise _StreamingUnderWriteLock()

                body_chunks: list[bytes] = []
                # body_iterator is always present on StreamingResponse from
                # call_next; the union type includes None only because the
                # base Response class doesn't guarantee it.
                async for chunk in response.body_iterator:  # type: ignore[union-attr]
                    body_chunks.append(chunk)
                body = b"".join(body_chunks)

                held = time.monotonic() - lock_start
                if held > LONG_LOCK_HOLD_THRESHOLD:
                    logger.warning(
                        "Write lock held %.1fs for %s %s -- consider @no_write_lock",
                        held,
                        request.method,
                        request.url.path,
                    )

                proxy = Response(
                    content=body,
                    status_code=response.status_code,
                    media_type=response.media_type,
                    background=response.background,
                )
                # Use raw_headers to preserve duplicate headers (e.g. Set-Cookie)
                # that dict(response.headers) would collapse.
                proxy.raw_headers = response.raw_headers
                return proxy

        except _StreamingUnderWriteLock:
            return Response(
                content=json.dumps(
                    {
                        "detail": "Internal error: streaming endpoint missing @no_write_lock decorator."
                    },
                    ensure_ascii=False,
                ),
                status_code=500,
                media_type="application/json",
            )
        except GitSyncError as e:
            status, message = self._map_error(e)
            return Response(
                content=json.dumps({"detail": message}, ensure_ascii=False),
                status_code=status,
                media_type="application/json",
            )

    async def _dev_mode_dirty_check(
        self,
        request: Request,
        response: Response,
        manager: GitSyncManager,
    ) -> Response:
        """In dev mode, surface missing write locks immediately.

        Runs only on the regular read path (not write-locked, not
        @no_write_lock). If the response is SSE, log the missing decorator.
        If the repo is dirty, log the offending request and return 500.
        """
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            logger.error(
                "DEV MODE: SSE endpoint missing @no_write_lock: %s %s",
                request.method,
                request.url.path,
            )
            return response

        dirty = await manager.get_dirty_file_paths()
        if dirty:
            logger.error(
                "DEV MODE: Request left repo dirty without write lock! "
                "(May also be caused by a parallel request with @no_write_lock "
                "mid-atomic_write — check all recent logs before blaming this request.)\n"
                "  API: %s %s\n  Project: %s\n  Dirty files: %s",
                request.method,
                request.url.path,
                manager.repo_path,
                dirty,
            )
            return Response(
                content=json.dumps(
                    {
                        "detail": "Dev mode: this endpoint wrote files without "
                        "holding a write lock, or a parallel request is "
                        "mid-write. See server logs for details."
                    },
                    ensure_ascii=False,
                ),
                status_code=500,
                media_type="application/json",
            )

        return response

    async def _unmatched_dispatch(self, request: Request, call_next) -> Response:
        """Handle requests whose URL does not match /api/projects/{id}/...

        In dev mode, after a mutating request completes, sweep all cached
        managers for dirty repos. A dirty repo here means the endpoint wrote
        project files but lives outside the middleware-matched URL prefix,
        silently bypassing git commit/push.

        Only detects projects whose manager is currently cached in the
        registry (i.e. accessed at least once this session). Projects
        configured for auto-sync but not yet opened would be missed.
        """
        response = await call_next(request)

        if not _is_dev_mode() or request.method not in MUTATING_METHODS:
            return response

        for mgr in GitSyncRegistry.all_managers():
            dirty = await mgr.get_dirty_file_paths()
            if dirty:
                logger.error(
                    "DEV MODE: Non-project-scoped endpoint wrote to a synced repo! "
                    "Endpoints that write project files MUST live under "
                    "/api/projects/{project_id}/... so GitSyncMiddleware can "
                    "commit and push changes.\n"
                    "(May also be caused by a parallel request with @no_write_lock "
                    "mid-atomic_write — check all recent logs before blaming this request.)\n"
                    "  API: %s %s\n  Repo: %s\n  Dirty files: %s",
                    request.method,
                    request.url.path,
                    mgr.repo_path,
                    dirty,
                )
                return Response(
                    content=json.dumps(
                        {
                            "detail": "Dev mode: a non-project-scoped endpoint wrote "
                            "to a synced repo without going through "
                            "GitSyncMiddleware. See server logs for details."
                        },
                        ensure_ascii=False,
                    ),
                    status_code=500,
                    media_type="application/json",
                )

        return response

    def _resolve_endpoint(self, request: Request) -> Callable[..., Any] | None:
        """Resolve the endpoint function for this request by matching routes.

        BaseHTTPMiddleware runs before routing, so request.scope["endpoint"]
        is not yet populated. We manually match against the app's routes to
        find the endpoint and read decorator attributes.

        Note: This performs a linear scan over all registered routes on each
        request. This is acceptable for typical apps with tens-to-low-hundreds
        of routes, but would need revisiting for very large route tables.
        """
        app = request.scope.get("app")
        if app is None:
            return None
        for route in app.routes:
            match, scope = route.matches(request.scope)
            if match == Match.FULL:
                return scope.get("endpoint")
        return None

    def _get_manager_for_request(self, request: Request) -> GitSyncManager | None:
        """Extract project_id from URL, resolve to path, return manager if auto-sync enabled."""
        match = PROJECT_ID_PATTERN.match(request.url.path)
        if match is None:
            return None

        project_id = match.group(1)
        project_path = project_path_from_id(project_id)
        if project_path is None:
            return None
        config = get_git_sync_config(project_path)
        if config is None:
            return None

        if config["sync_mode"] != "auto":
            return None

        clone_path = config.get("clone_path")
        if clone_path is None:
            return None

        return GitSyncRegistry.get_or_create(
            repo_path=Path(clone_path),
            remote_name=config["remote_name"],
            pat_token=config.get("pat_token"),
            oauth_token=config.get("oauth_token"),
            auth_mode=config["auth_mode"],
        )

    def _notify_background_sync(self, manager: GitSyncManager) -> None:
        """Notify background sync of activity to prevent idle pause."""
        bg_sync = GitSyncRegistry.get_background_sync(manager.repo_path)
        if bg_sync is not None:
            bg_sync.notify_request()

    def _map_error(self, error: GitSyncError) -> tuple[int, str]:
        for error_type, (status, message) in ERROR_MAP.items():
            if isinstance(error, error_type):
                return status, message
        return 500, "An unexpected git sync error occurred."
