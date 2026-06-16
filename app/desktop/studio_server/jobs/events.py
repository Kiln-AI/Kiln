from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Callable, Literal

from pydantic import BaseModel

from .models import JobRecord


class JobEvent(BaseModel):
    """A single bus event. Per-job events carry the full record (idempotent snapshot)."""

    event: Literal["snapshot", "job", "deleted", "ping"]
    data: dict[str, Any]


class _CloseSentinel:
    """Pushed onto a subscriber's queue by ``shutdown()`` to end its stream
    promptly (e.g. so a dev-server hot reload isn't blocked by open SSE
    connections), distinct from a normal ``JobEvent``."""


_CLOSE = _CloseSentinel()


class _Subscriber:
    def __init__(
        self,
        job_id: str | None,
        type_name: str | None,
        project_id: str | None,
    ) -> None:
        self.queue: asyncio.Queue[JobEvent | _CloseSentinel] = asyncio.Queue()
        self.job_id = job_id
        self.type_name = type_name
        self.project_id = project_id

    def matches(
        self,
        record_id: str | None,
        record_type: str | None,
        record_project_id: str | None,
    ) -> bool:
        if self.job_id is not None and self.job_id != record_id:
            return False
        if self.type_name is not None and self.type_name != record_type:
            return False
        if self.project_id is not None and self.project_id != record_project_id:
            return False
        return True


SnapshotProvider = Callable[[], list[JobRecord]]


class JobEventBus:
    """In-process async pub/sub bus feeding the SSE endpoint (Phase 2).

    Subscribers receive an initial `snapshot` event, then per-job `job` events
    and `deleted` tombstones, filtered by job_id / type / project_id.
    """

    def __init__(self, snapshot_provider: SnapshotProvider | None = None) -> None:
        self._subscribers: set[_Subscriber] = set()
        self._snapshot_provider = snapshot_provider
        self._closed = False

    def set_snapshot_provider(self, provider: SnapshotProvider) -> None:
        self._snapshot_provider = provider

    def _filtered_snapshot(self, subscriber: _Subscriber) -> list[JobRecord]:
        if self._snapshot_provider is None:
            return []
        return [
            record
            for record in self._snapshot_provider()
            if subscriber.matches(record.id, record.type, record.project_id)
        ]

    async def subscribe(
        self,
        job_id: str | None = None,
        type_name: str | None = None,
        project_id: str | None = None,
        timeout: float | None = None,
    ) -> AsyncGenerator[JobEvent, None]:
        """Yield the initial snapshot then per-job events.

        When ``timeout`` is set, a ``ping`` event is yielded after that many
        seconds without a real event. The timeout MUST live here, inside the
        generator: cancelling ``subscribe().__anext__()` from the outside (e.g.
        ``asyncio.wait_for``) throws CancelledError into the suspended generator,
        runs its ``finally``, and finalizes it — so the very next ``__anext__``
        would raise StopAsyncIteration and kill the stream after one ping.

        The generator ends (returns) when ``shutdown()`` has been called: either
        immediately if the bus is already closed, or as soon as the close
        sentinel reaches the head of the queue.
        """
        if self._closed:
            return
        subscriber = _Subscriber(job_id, type_name, project_id)
        self._subscribers.add(subscriber)
        try:
            snapshot = self._filtered_snapshot(subscriber)
            yield JobEvent(
                event="snapshot",
                data={"jobs": [r.model_dump(mode="json") for r in snapshot]},
            )
            while True:
                if timeout is None:
                    item = await subscriber.queue.get()
                else:
                    try:
                        item = await asyncio.wait_for(
                            subscriber.queue.get(), timeout=timeout
                        )
                    except asyncio.TimeoutError:
                        yield JobEvent(event="ping", data={})
                        continue
                if isinstance(item, _CloseSentinel):
                    return
                yield item
        finally:
            self._subscribers.discard(subscriber)

    def shutdown(self) -> None:
        """End every open subscription and reject new ones.

        Pushes a close sentinel onto each subscriber's queue so its
        ``subscribe()`` generator returns promptly. Used on server shutdown so a
        long-lived SSE connection (the jobs stream the UI holds open) doesn't
        keep the worker alive — e.g. blocking a dev-server hot reload. A pure
        observer teardown: it never touches any job's supervising task.
        """
        self._closed = True
        for subscriber in self._subscribers:
            subscriber.queue.put_nowait(_CLOSE)

    def publish_job(self, record: JobRecord) -> None:
        event = JobEvent(event="job", data=record.model_dump(mode="json"))
        for subscriber in self._subscribers:
            if subscriber.matches(record.id, record.type, record.project_id):
                subscriber.queue.put_nowait(event)

    def publish_deleted(
        self,
        job_id: str,
        type_name: str | None = None,
        project_id: str | None = None,
    ) -> None:
        event = JobEvent(event="deleted", data={"id": job_id})
        for subscriber in self._subscribers:
            if subscriber.matches(job_id, type_name, project_id):
                subscriber.queue.put_nowait(event)
