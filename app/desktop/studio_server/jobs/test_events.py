from __future__ import annotations

import asyncio

import pytest
from app.desktop.studio_server.jobs.events import (
    JobEvent,
    JobEventBus,
    KeepalivePing,
    iter_with_keepalive,
)
from app.desktop.studio_server.jobs.models import BackgroundJobStatus, JobRecord


def _record(
    job_id: str = "j_aaaaaaaaaaaa",
    type_name: str = "noop",
    project_id: str | None = None,
    status: BackgroundJobStatus = BackgroundJobStatus.RUNNING,
) -> JobRecord:
    return JobRecord(
        id=job_id,
        type=type_name,
        status=status,
        project_id=project_id,
    )


async def _next_event(gen, timeout: float = 1.0) -> JobEvent:
    return await asyncio.wait_for(gen.__anext__(), timeout=timeout)


@pytest.mark.asyncio
async def test_snapshot_then_job_event():
    existing = _record("j_existing0001")
    bus = JobEventBus(snapshot_provider=lambda: [existing])

    gen = bus.subscribe()
    snapshot = await _next_event(gen)
    assert snapshot.event == "snapshot"
    assert [j["id"] for j in snapshot.data["jobs"]] == ["j_existing0001"]

    new = _record("j_new000000001")
    bus.publish_job(new)
    job_event = await _next_event(gen)
    assert job_event.event == "job"
    assert job_event.data["id"] == "j_new000000001"

    await gen.aclose()


@pytest.mark.asyncio
async def test_deleted_event():
    bus = JobEventBus(snapshot_provider=lambda: [])
    gen = bus.subscribe()
    await _next_event(gen)  # snapshot

    bus.publish_deleted("j_gone00000001")
    event = await _next_event(gen)
    assert event.event == "deleted"
    assert event.data == {"id": "j_gone00000001"}

    await gen.aclose()


@pytest.mark.asyncio
async def test_filter_by_project_id():
    matching = _record("j_match0000001", project_id="p_keep")
    other = _record("j_other0000001", project_id="p_drop")
    bus = JobEventBus(snapshot_provider=lambda: [matching, other])

    gen = bus.subscribe(project_id="p_keep")
    snapshot = await _next_event(gen)
    assert [j["id"] for j in snapshot.data["jobs"]] == ["j_match0000001"]

    bus.publish_job(other)
    bus.publish_job(matching)
    event = await _next_event(gen)
    assert event.data["id"] == "j_match0000001"

    await gen.aclose()


@pytest.mark.asyncio
async def test_filter_by_type_and_job_id():
    bus = JobEventBus(snapshot_provider=lambda: [])
    gen = bus.subscribe(type_name="eval", job_id="j_target000001")
    await _next_event(gen)  # snapshot

    bus.publish_job(_record("j_other0000001", type_name="noop"))
    bus.publish_job(_record("j_target000001", type_name="eval"))
    event = await _next_event(gen)
    assert event.data["id"] == "j_target000001"

    await gen.aclose()


@pytest.mark.asyncio
async def test_keepalive_ping_does_not_finalize_generator():
    # Regression: iter_with_keepalive must yield KeepalivePing sentinels on quiet
    # windows while keeping the underlying subscription alive — not finalize it
    # after the first one.
    bus = JobEventBus(snapshot_provider=lambda: [])
    gen = iter_with_keepalive(bus.subscribe(), 0.02)

    async def _next():
        return await asyncio.wait_for(gen.__anext__(), timeout=1.0)

    first = await _next()
    assert isinstance(first, JobEvent) and first.event == "snapshot"
    assert isinstance(await _next(), KeepalivePing)
    assert isinstance(await _next(), KeepalivePing)

    # A real event still flows after pings.
    bus.publish_job(_record("j_after000001"))
    event = await _next()
    assert isinstance(event, JobEvent)
    assert event.event == "job"
    assert event.data["id"] == "j_after000001"

    await gen.aclose()


@pytest.mark.asyncio
async def test_shutdown_ends_open_stream_and_rejects_new_ones():
    bus = JobEventBus(snapshot_provider=lambda: [])
    gen = bus.subscribe()
    assert (await _next_event(gen)).event == "snapshot"

    # shutdown() pushes a close sentinel so the open generator returns.
    bus.shutdown()
    with pytest.raises(StopAsyncIteration):
        await _next_event(gen)

    # A subscription opened after shutdown ends immediately (no snapshot).
    gen2 = bus.subscribe()
    with pytest.raises(StopAsyncIteration):
        await _next_event(gen2)


@pytest.mark.asyncio
async def test_shutdown_unblocks_subscriber_waiting_without_timeout():
    # With no keepalive timeout the subscriber blocks on queue.get(); shutdown()
    # must still wake it so a hot reload isn't held open.
    bus = JobEventBus(snapshot_provider=lambda: [])
    gen = bus.subscribe()  # timeout=None
    assert (await _next_event(gen)).event == "snapshot"

    async def _drain():
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    waiter = asyncio.ensure_future(_drain())
    await asyncio.sleep(0)  # let the waiter block on queue.get()
    bus.shutdown()
    await asyncio.wait_for(waiter, timeout=1.0)
