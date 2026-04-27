from contextlib import asynccontextmanager

import pytest
from starlette.requests import Request

from kiln_server.git_sync_decorators import (
    build_save_context,
    no_write_lock,
    write_lock,
)


def _make_request(state: dict | None = None) -> Request:
    """Build a minimal starlette Request with a populated state and URL."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/projects/abc/test",
        "raw_path": b"/api/projects/abc/test",
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
        "app": None,
        "state": state if state is not None else {},
    }
    return Request(scope)


def test_write_lock_sets_attribute():
    @write_lock
    def endpoint():
        pass

    assert getattr(endpoint, "_git_sync_write_lock", False) is True


def test_no_write_lock_sets_attribute():
    @no_write_lock
    def endpoint():
        pass

    assert getattr(endpoint, "_git_sync_no_write_lock", False) is True


def test_write_lock_preserves_function():
    @write_lock
    def endpoint():
        return 42

    assert endpoint() == 42


def test_no_write_lock_preserves_function():
    @no_write_lock
    def endpoint():
        return 99

    assert endpoint() == 99


def test_undecorated_has_no_attributes():
    def endpoint():
        pass

    assert getattr(endpoint, "_git_sync_write_lock", False) is False
    assert getattr(endpoint, "_git_sync_no_write_lock", False) is False


def test_build_save_context_returns_none_without_manager():
    request = _make_request()
    assert build_save_context(request) is None


def test_build_save_context_returns_none_when_explicit_none():
    request = _make_request()
    request.state.git_sync_manager = None
    assert build_save_context(request) is None


class _RecordingManager:
    """Duck-typed AtomicWriteCapable for tests -- records enter/exit/context."""

    def __init__(self):
        self.entered = 0
        self.exited = 0
        self.received_context: str | None = None
        self.last_exc: BaseException | None = None

    def atomic_write(self, context: str):
        self.received_context = context

        @asynccontextmanager
        async def cm():
            self.entered += 1
            try:
                yield
            except BaseException as exc:
                self.last_exc = exc
                self.exited += 1
                raise
            else:
                self.exited += 1

        return cm()


@pytest.mark.asyncio
async def test_build_save_context_returns_factory_with_manager():
    manager = _RecordingManager()
    request = _make_request()
    request.state.git_sync_manager = manager

    factory = build_save_context(request)
    assert factory is not None

    async with factory():
        pass

    assert manager.entered == 1
    assert manager.exited == 1
    assert manager.received_context == "POST /api/projects/abc/test"
    assert manager.last_exc is None


@pytest.mark.asyncio
async def test_build_save_context_propagates_exception():
    manager = _RecordingManager()
    request = _make_request()
    request.state.git_sync_manager = manager

    factory = build_save_context(request)
    assert factory is not None

    with pytest.raises(ValueError):
        async with factory():
            raise ValueError("boom")

    assert manager.entered == 1
    assert manager.exited == 1
    assert isinstance(manager.last_exc, ValueError)


@pytest.mark.asyncio
async def test_build_save_context_rebuilds_each_call():
    """Each call to the factory should enter a fresh atomic_write context."""
    manager = _RecordingManager()
    request = _make_request()
    request.state.git_sync_manager = manager

    factory = build_save_context(request)
    assert factory is not None

    async with factory():
        pass
    async with factory():
        pass

    assert manager.entered == 2
    assert manager.exited == 2


@pytest.mark.asyncio
async def test_build_save_context_uses_method_and_path_in_context():
    """The context string is derived from request method + path."""
    manager = _RecordingManager()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/projects/xyz/run",
        "raw_path": b"/api/projects/xyz/run",
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
        "app": None,
        "state": {},
    }
    request = Request(scope)
    request.state.git_sync_manager = manager

    factory = build_save_context(request)
    assert factory is not None

    async with factory():
        pass

    assert manager.received_context == "GET /api/projects/xyz/run"
