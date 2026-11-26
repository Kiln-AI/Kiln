"""The models.dev catalogue, loaded on demand and held in memory.

There is no timer and no load at start: the first request that finds no data,
or data older than `max_age`, starts one load and waits for it, at most
`wait_secs`. Requests that arrive while it runs wait for the same load. A
load that fails keeps the last good data, and none starts again until the
retry interval has passed, so an outage costs one wait, not one per request.
The GET is a plain conditional GET of a public file: it sends no header of
ours beyond `If-None-Match`, and no query string.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Protocol

import httpx

from app.desktop.studio_server.services.model_info.catalog_build import (
    ModelsDevData,
    parse_models_dev,
)

logger = logging.getLogger(__name__)

MODELS_DEV_URL = "https://models.dev/api.json"

ModelsDevState = Literal["ok", "stale", "unavailable"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=True)


@dataclass(frozen=True)
class ModelsDevSnapshot:
    data: ModelsDevData | None
    state: ModelsDevState
    # UTC time the data was fetched, or last confirmed unchanged by a 304.
    loaded_at: datetime | None
    # None when `ok`; else why the data is missing or old.
    detail: str | None


class ModelsDevSource(Protocol):
    async def current(self) -> ModelsDevSnapshot: ...


class ModelsDevCache:
    """In-memory models.dev data with a single-flight, on-demand refresh.
    Created with the app; `aclose()` at shutdown cancels a refresh in flight.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        url: str = MODELS_DEV_URL,
        max_age: timedelta = timedelta(hours=6),
        retry_after: timedelta = timedelta(minutes=10),
        retry_after_empty: timedelta = timedelta(minutes=1),
        wait_secs: float = 15.0,
        fetch_timeout_secs: float = 30.0,
        max_bytes: int = 50 * 1024 * 1024,
        now: Callable[[], datetime] = utc_now,
        client_factory: Callable[[], httpx.AsyncClient] = default_client,
    ) -> None:
        self._enabled = enabled
        self._url = url
        self._max_age = max_age
        self._retry_after = retry_after
        self._retry_after_empty = retry_after_empty
        self._wait_secs = wait_secs
        self._fetch_timeout_secs = fetch_timeout_secs
        self._max_bytes = max_bytes
        self._now = now
        self._client_factory = client_factory
        self._data: ModelsDevData | None = None
        self._etag: str | None = None
        self._loaded_at: datetime | None = None
        self._last_failure: str | None = None
        self._last_failure_at: datetime | None = None
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def current(self) -> ModelsDevSnapshot:
        """The data to answer a request with. Starts a load when there is no
        data or it is older than `max_age`, and waits up to `wait_secs` for a
        load that is running. Never raises."""
        if not self._enabled:
            return ModelsDevSnapshot(
                data=None, state="unavailable", loaded_at=None, detail="turned off"
            )
        now = self._now()
        if self._needs_load(now) and not self._closed:
            task = self._running_task()
            if task is None and self._may_start_load(now):
                # No await between the check above and this line, so one event
                # loop never runs two loads.
                task = self._task = asyncio.create_task(self._refresh())
            if task is not None:
                # A timeout leaves the load running; a later request gets it.
                await asyncio.wait({task}, timeout=self._wait_secs)
        return self._snapshot()

    async def settle(self) -> None:
        """Wait for a load in flight, if any."""
        task = self._running_task()
        if task is not None:
            await asyncio.wait({task})

    async def aclose(self) -> None:
        """Cancel a load in flight; later calls start none. Never raises."""
        self._closed = True
        task = self._running_task()
        if task is not None:
            task.cancel()
            await asyncio.wait({task})

    def _needs_load(self, now: datetime) -> bool:
        return self._loaded_at is None or now - self._loaded_at >= self._max_age

    def _running_task(self) -> asyncio.Task[None] | None:
        """The load in flight on this event loop. A task of another loop is
        ignored: Starlette's `TestClient` used without `with` runs each
        request on a new loop."""
        task = self._task
        if task is None or task.done():
            return None
        try:
            if task.get_loop() is not asyncio.get_running_loop():
                return None
        except RuntimeError:
            return None
        return task

    def _may_start_load(self, now: datetime) -> bool:
        if self._last_failure_at is None:
            return True
        interval = (
            self._retry_after if self._data is not None else self._retry_after_empty
        )
        return now - self._last_failure_at >= interval

    def _snapshot(self) -> ModelsDevSnapshot:
        loading = self._running_task() is not None
        if self._data is None:
            detail = "loading" if loading else self._last_failure or "not loaded"
            return ModelsDevSnapshot(
                data=None, state="unavailable", loaded_at=None, detail=detail
            )
        if not self._needs_load(self._now()):
            return ModelsDevSnapshot(
                data=self._data, state="ok", loaded_at=self._loaded_at, detail=None
            )
        detail = "refresh running" if loading else self._last_failure
        return ModelsDevSnapshot(
            data=self._data, state="stale", loaded_at=self._loaded_at, detail=detail
        )

    async def _refresh(self) -> None:
        try:
            failure = await asyncio.wait_for(self._fetch(), self._fetch_timeout_secs)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            failure = f"timeout after {self._fetch_timeout_secs:g} s"
        except httpx.HTTPError as e:
            failure = f"transport error: {type(e).__name__}"
        except Exception as e:
            failure = f"fetch failed: {type(e).__name__}"
        if failure is None:
            self._last_failure = None
            self._last_failure_at = None
            return
        self._last_failure = failure
        self._last_failure_at = self._now()
        logger.warning("Could not load models.dev model data: %s", failure)

    async def _fetch(self) -> str | None:
        """Load the data. Returns the failure reason, or None on success."""
        headers = {}
        if self._data is not None and self._etag is not None:
            headers["If-None-Match"] = self._etag
        async with self._client_factory() as client:
            async with client.stream("GET", self._url, headers=headers) as response:
                if response.status_code == 304 and self._data is not None:
                    self._loaded_at = self._now()
                    return None
                if response.status_code != 200:
                    return f"HTTP {response.status_code}"
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > self._max_bytes:
                        return f"body over {self._max_bytes // (1024 * 1024)} MiB"
                etag = response.headers.get("etag")
        try:
            data = await asyncio.to_thread(parse_models_dev, bytes(body))
        except ValueError as e:
            return str(e)
        self._data = data
        self._etag = etag
        self._loaded_at = self._now()
        return None
