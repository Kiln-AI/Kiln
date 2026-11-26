import asyncio

import pytest

from kiln_mcp_server.api_tool.progress import run_with_progress


class Recorder:
    def __init__(self) -> None:
        self.updates: list[tuple[float, float | None, str | None]] = []

    async def __call__(
        self, progress: float, total: float | None, message: str | None
    ) -> None:
        self.updates.append((progress, total, message))


async def finish_after(seconds: float, value: str = "done") -> str:
    await asyncio.sleep(seconds)
    return value


async def test_no_update_when_the_call_ends_first():
    send = Recorder()
    assert (
        await run_with_progress(finish_after(0), send, label="GET /ping", interval=1)
        == "done"
    )
    assert send.updates == []


async def test_updates_while_a_slow_call_runs():
    send = Recorder()
    await run_with_progress(finish_after(0.2), send, label="GET /x", interval=0.03)
    assert len(send.updates) >= 3
    assert send.updates[0] == (1.0, None, "GET /x: still running, 0 s")
    assert [update[0] for update in send.updates] == [
        float(n) for n in range(1, len(send.updates) + 1)
    ]


async def test_no_sender():
    assert (
        await run_with_progress(finish_after(0.05), None, label="x", interval=0.01)
        == "done"
    )


async def test_a_failing_sender_does_not_fail_the_call():
    calls = 0

    async def broken(progress: float, total: float | None, message: str | None):
        nonlocal calls
        calls += 1
        raise RuntimeError("client gone")

    assert (
        await run_with_progress(finish_after(0.1), broken, label="x", interval=0.01)
        == "done"
    )
    assert calls == 1


async def test_cancelling_the_caller_cancels_the_work():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def work() -> None:
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    caller = asyncio.ensure_future(
        run_with_progress(work(), None, label="x", interval=0.01)
    )
    await started.wait()
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    await asyncio.wait_for(cancelled.wait(), timeout=1)


async def test_the_work_exception_propagates():
    async def fails() -> None:
        await asyncio.sleep(0.02)
        raise ValueError("bad")

    with pytest.raises(ValueError, match="bad"):
        await run_with_progress(fails(), Recorder(), label="x", interval=0.01)
