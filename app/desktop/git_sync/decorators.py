from typing import Callable, TypeVar

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
