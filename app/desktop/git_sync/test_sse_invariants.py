import os
import tempfile
import types
import typing
from typing import Union, get_args, get_origin, get_type_hints
from unittest.mock import patch

from fastapi.routing import APIRoute
from starlette.responses import StreamingResponse

from app.desktop.desktop_server import make_app
from app.desktop.git_sync.middleware import PROJECT_ID_PATTERN


def _contains_streaming_response(tp: type) -> bool:
    if isinstance(tp, type) and issubclass(tp, StreamingResponse):
        return True
    origin = get_origin(tp)
    if origin is Union or origin is types.UnionType:
        return any(_contains_streaming_response(a) for a in get_args(tp))
    return False


def _return_type_is_streaming(fn: typing.Callable) -> bool:
    try:
        hints = get_type_hints(fn)
    except Exception:
        return False
    ret = hints.get("return")
    if ret is None:
        return False
    return _contains_streaming_response(ret)


def _is_project_scoped(route: APIRoute) -> bool:
    """Check if a route's path matches the middleware's project URL pattern.

    Only project-scoped routes flow through the middleware's lock logic.
    Non-project-scoped streaming routes (e.g. /api/chat) are passed
    through by _unmatched_dispatch and are not affected.
    """
    return PROJECT_ID_PATTERN.match(route.path) is not None


def test_streaming_routes_require_no_write_lock():
    """Every project-scoped route returning StreamingResponse must be
    @no_write_lock.

    Without @no_write_lock, GitSyncMiddleware falls through to
    BaseHTTPMiddleware.dispatch which wraps receive/send and prevents
    client-disconnect cancellation from reaching the SSE stream.

    Only checks routes matching /api/projects/{id}/... since those are
    the only ones routed through the middleware's lock logic.
    """
    with (
        tempfile.TemporaryDirectory() as temp_dir,
        patch("app.desktop.desktop_server.refresh_model_list_background"),
        patch(
            "app.desktop.studio_server.webhost.studio_path",
            new=lambda: temp_dir,
        ),
    ):
        os.makedirs(temp_dir, exist_ok=True)
        app = make_app()

    offenders = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not _is_project_scoped(route):
            continue
        if not _return_type_is_streaming(route.endpoint):
            continue
        if not getattr(route.endpoint, "_git_sync_no_write_lock", False):
            offenders.append(f"{route.methods} {route.path}")

    assert not offenders, (
        "Routes return StreamingResponse but are not @no_write_lock:\n  "
        + "\n  ".join(offenders)
        + "\n\nAdd @no_write_lock to the route handler; otherwise "
        "GitSyncMiddleware will buffer the stream and client disconnects "
        "will not cancel in-flight workers."
    )
