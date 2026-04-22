import asyncio

import pytest

from kiln_server import sse


@pytest.mark.asyncio
async def test_stream_with_heartbeat_forwards_items():
    async def source():
        yield 1
        yield 2
        yield 3

    collected = []
    async for chunk in sse.stream_with_heartbeat(source(), lambda i: f"item:{i}"):
        collected.append(chunk)

    assert collected == ["item:1", "item:2", "item:3"]


@pytest.mark.asyncio
async def test_stream_with_heartbeat_emits_heartbeat_on_idle():
    """When the source is silent longer than heartbeat_seconds, emit keepalive."""

    async def slow_source():
        await asyncio.sleep(0.2)
        yield "done"

    collected = []
    async for chunk in sse.stream_with_heartbeat(
        slow_source(), lambda s: f"data:{s}", heartbeat_seconds=0.05
    ):
        collected.append(chunk)
        if len(collected) > 20:  # safety
            break

    assert sse.HEARTBEAT_COMMENT in collected
    assert collected[-1] == "data:done"


@pytest.mark.asyncio
async def test_stream_with_heartbeat_closes_source_on_normal_exit():
    """Source aclose() must run in the wrapper's finally block so the source's
    own finally (e.g. AsyncJobRunner's worker cancellation) runs.
    """
    closed = False

    async def source():
        nonlocal closed
        try:
            yield 1
            yield 2
        finally:
            closed = True

    async for _ in sse.stream_with_heartbeat(source(), lambda i: str(i)):
        pass

    assert closed is True


@pytest.mark.asyncio
async def test_stream_with_heartbeat_closes_source_on_aclose():
    """aclose() on the wrapper must also aclose the source."""
    closed = False

    async def source():
        nonlocal closed
        try:
            while True:
                await asyncio.sleep(10)
                yield "never"
        finally:
            closed = True

    wrapper = sse.stream_with_heartbeat(source(), lambda s: s, heartbeat_seconds=0.05)

    # Pull one heartbeat to get the wrapper into its waiting state.
    first = await wrapper.__anext__()
    assert first == sse.HEARTBEAT_COMMENT

    await wrapper.aclose()
    assert closed is True


@pytest.mark.asyncio
async def test_stream_with_heartbeat_exits_when_is_disconnected():
    """When the is_disconnected callable returns True, the wrapper exits and
    closes the source — so AsyncJobRunner's finally block runs.
    """
    closed = False

    async def source():
        nonlocal closed
        try:
            while True:
                await asyncio.sleep(0.01)
                yield "tick"
        finally:
            closed = True

    poll_count = {"n": 0}

    async def is_disconnected():
        poll_count["n"] += 1
        return poll_count["n"] >= 2

    collected = []
    async for chunk in sse.stream_with_heartbeat(
        source(),
        lambda s: s,
        heartbeat_seconds=0.05,
        is_disconnected=is_disconnected,
    ):
        collected.append(chunk)
        if len(collected) > 50:  # safety
            break

    assert closed is True
