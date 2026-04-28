import asyncio

import pytest
from starlette.background import BackgroundTask
from starlette.types import Message

from kiln_server.cancellable_streaming_response import CancellableStreamingResponse


def _http_scope(spec_version: str = "2.4") -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "method": "GET",
        "path": "/",
        "headers": [],
    }


def _never_disconnect_receive():
    """A receive callable that blocks forever (no disconnect)."""

    async def receive() -> Message:
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}  # pragma: no cover

    return receive


@pytest.mark.asyncio
async def test_streams_response_when_no_disconnect():
    finally_ran = asyncio.Event()

    async def generator():
        try:
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"
        finally:
            finally_ran.set()

    response = CancellableStreamingResponse(
        content=generator(),
        media_type="text/event-stream",
    )

    scope = _http_scope()
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    async with asyncio.timeout(5):
        await response(scope, _never_disconnect_receive(), send)

    assert finally_ran.is_set()
    bodies = [m for m in sent if m["type"] == "http.response.body"]
    body_bytes = b"".join(b.get("body", b"") for b in bodies)
    assert b"chunk1" in body_bytes
    assert b"chunk2" in body_bytes
    assert b"chunk3" in body_bytes


@pytest.mark.asyncio
async def test_cancels_generator_on_client_disconnect():
    finally_ran = asyncio.Event()

    async def slow_generator():
        try:
            yield b"data: chunk1\n\n"
            await asyncio.sleep(30)
            yield b"data: chunk2\n\n"
        finally:
            finally_ran.set()

    response = CancellableStreamingResponse(
        content=slow_generator(),
        media_type="text/event-stream",
    )

    scope = _http_scope()
    sent: list[Message] = []
    first_body_sent = asyncio.Event()

    async def send(message: Message) -> None:
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            first_body_sent.set()

    async def receive() -> Message:
        await first_body_sent.wait()
        await asyncio.sleep(0.05)
        return {"type": "http.disconnect"}

    async with asyncio.timeout(5):
        await response(scope, receive, send)

    assert finally_ran.is_set(), "generator's finally did not run on disconnect"
    bodies = [m for m in sent if m["type"] == "http.response.body"]
    assert any(b.get("body") == b"data: chunk1\n\n" for b in bodies)
    assert not any(b.get("body") == b"data: chunk2\n\n" for b in bodies)


@pytest.mark.asyncio
async def test_background_task_runs_after_completion():
    background_ran = asyncio.Event()

    async def do_background():
        background_ran.set()

    async def generator():
        yield b"done"

    response = CancellableStreamingResponse(
        content=generator(),
        media_type="text/event-stream",
        background=BackgroundTask(do_background),
    )

    scope = _http_scope()
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    async with asyncio.timeout(5):
        await response(scope, _never_disconnect_receive(), send)

    assert background_ran.is_set(), "background task did not run"


@pytest.mark.asyncio
@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_no_spec_version_branching(spec_version: str):
    finally_ran = asyncio.Event()

    async def slow_generator():
        try:
            yield b"data: chunk1\n\n"
            await asyncio.sleep(30)
            yield b"data: chunk2\n\n"
        finally:
            finally_ran.set()

    response = CancellableStreamingResponse(
        content=slow_generator(),
        media_type="text/event-stream",
    )

    scope = _http_scope(spec_version=spec_version)
    sent: list[Message] = []
    first_body_sent = asyncio.Event()

    async def send(message: Message) -> None:
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            first_body_sent.set()

    async def receive() -> Message:
        await first_body_sent.wait()
        await asyncio.sleep(0.05)
        return {"type": "http.disconnect"}

    async with asyncio.timeout(5):
        await response(scope, receive, send)

    assert finally_ran.is_set(), (
        f"generator's finally did not run on disconnect with spec_version={spec_version}"
    )
    bodies = [m for m in sent if m["type"] == "http.response.body"]
    assert any(b.get("body") == b"data: chunk1\n\n" for b in bodies)
    assert not any(b.get("body") == b"data: chunk2\n\n" for b in bodies)


@pytest.mark.asyncio
async def test_exception_in_generator_propagates():
    async def bad_generator():
        yield b"ok"
        raise ValueError("boom")

    response = CancellableStreamingResponse(
        content=bad_generator(),
        media_type="text/event-stream",
    )

    scope = _http_scope()
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    async with asyncio.timeout(5):
        with pytest.raises(ValueError, match="boom"):
            await response(scope, _never_disconnect_receive(), send)
