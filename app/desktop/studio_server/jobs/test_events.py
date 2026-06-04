from __future__ import annotations

import asyncio

import pytest
from app.desktop.studio_server.jobs.events import JobEvent, JobEventBus
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
