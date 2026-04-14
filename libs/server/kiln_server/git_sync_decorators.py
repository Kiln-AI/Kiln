from typing import Callable, TypeVar

from fastapi import Request
from kiln_ai.utils.git_sync_protocols import AtomicWriteCapable, SaveContext

F = TypeVar("F", bound=Callable)


def write_lock(fn: F) -> F:
    """Mark a GET endpoint as requiring the git sync write lock.

    Use on GET endpoints that perform mutations (e.g., browser limitations
    requiring GET for a mutating action).
    """
    fn._git_sync_write_lock = True  # type: ignore[attr-defined]
    return fn


def no_write_lock(fn: F) -> F:
    """Mark a mutating endpoint as NOT requiring the git sync write lock.

    Use on long-running endpoints (e.g., SSE eval batch jobs) that manage
    their own lock scopes and commit cycle.
    """
    fn._git_sync_no_write_lock = True  # type: ignore[attr-defined]
    return fn


def build_save_context(request: Request) -> SaveContext | None:
    """Return a SaveContext that wraps writes in manager.atomic_write(...),
    or None if git sync is not active for this request.

    The endpoint passes the returned value to its runner; the runner
    defaults to a no-op context when None.
    """
    manager: AtomicWriteCapable | None = getattr(
        request.state, "git_sync_manager", None
    )
    if manager is None:
        return None

    context = f"{request.method} {request.url.path}"

    def factory():
        return manager.atomic_write(context=context)

    return factory
