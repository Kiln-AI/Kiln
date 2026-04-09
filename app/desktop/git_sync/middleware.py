import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

from app.desktop.git_sync.config import get_git_sync_config
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
            return await call_next(request)

        endpoint = self._resolve_endpoint(request)
        needs_lock = (
            request.method in MUTATING_METHODS
            or getattr(endpoint, "_git_sync_write_lock", False)
        ) and not getattr(endpoint, "_git_sync_no_write_lock", False)

        if not needs_lock:
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
            return await call_next(request)

        self._notify_background_sync(manager)
        lock_start = time.monotonic()
        async with manager.write_lock():
            await manager.ensure_clean()
            await manager.ensure_fresh()

            pre_request_head = await manager.get_head()

            try:
                response = await call_next(request)

                # Detect streaming responses before consuming body
                # SSE streams must not be returned under the write lock:
                # the lock would be held for the entire stream duration,
                # blocking all other mutating requests. Mark SSE endpoints
                # with @no_write_lock to avoid this path entirely.
                if (
                    hasattr(response, "media_type")
                    and response.media_type == "text/event-stream"
                ):
                    logger.error(
                        "Streaming response under write lock for %s %s -- "
                        "use @no_write_lock instead",
                        request.method,
                        request.url.path,
                    )
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

                body = b""
                # body_iterator is always present on StreamingResponse from
                # call_next; the union type includes None only because the
                # base Response class doesn't guarantee it.
                async for chunk in response.body_iterator:  # type: ignore[union-attr]
                    body += chunk

                # TODO: gate on dev_mode when that mechanism exists
                held = time.monotonic() - lock_start
                if held > LONG_LOCK_HOLD_THRESHOLD:
                    logger.warning(
                        "Write lock held %.1fs for %s %s -- consider @no_write_lock",
                        held,
                        request.method,
                        request.url.path,
                    )

                has_changes = await manager.has_dirty_files()
                if has_changes:
                    await manager.commit_and_push(
                        api_path=f"{request.method} {request.url.path}",
                        pre_request_head=pre_request_head,
                    )

                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

            except Exception as e:
                await manager.rollback(pre_request_head)
                if isinstance(e, GitSyncError):
                    status, message = self._map_error(e)
                    return Response(
                        content=json.dumps({"detail": message}, ensure_ascii=False),
                        status_code=status,
                        media_type="application/json",
                    )
                raise

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
        """Extract project_id from URL, return manager if auto-sync enabled."""
        match = PROJECT_ID_PATTERN.match(request.url.path)
        if match is None:
            return None

        project_id = match.group(1)
        config = get_git_sync_config(project_id)
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
            auth_mode=config.get("auth_mode", "system_keys"),
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
