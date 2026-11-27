import asyncio
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from app.desktop.studio_server.services.model_info.models_dev import (
    MODELS_DEV_URL,
    ModelsDevCache,
)
from app.desktop.studio_server.services.model_info.test_catalog_build import (
    models_dev_file,
)

BODY = json.dumps(models_dev_file(), ensure_ascii=False).encode()
OTHER_BODY = json.dumps({"openai": {"models": {"x": {}}}}, ensure_ascii=False).encode()
# The headers httpx sends on its own; the cache adds none but If-None-Match.
HTTPX_DEFAULT_HEADERS = {
    "host",
    "accept",
    "accept-encoding",
    "connection",
    "user-agent",
}
STALL_SECS = 0.05


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class FakeServer:
    """A models.dev stand-in: records each request and answers with the
    current `reply`. While `stalled`, a request waits for `release()`."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.reply: Callable[[httpx.Request], httpx.Response] = ok(BODY, "v1")
        self.stalled = False
        self._released = asyncio.Event()

    def release(self) -> None:
        self._released.set()

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.stalled:
            await self._released.wait()
        return self.reply(request)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))


def ok(body: bytes, etag: str | None) -> Callable[[httpx.Request], httpx.Response]:
    headers = {"ETag": etag} if etag else {}
    return lambda request: httpx.Response(200, content=body, headers=headers)


def reply_status(code: int) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(code)


def raise_error(error: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def reply(request: httpx.Request) -> httpx.Response:
        raise error

    return reply


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def make_cache(clock, server):
    def make(**options) -> ModelsDevCache:
        return ModelsDevCache(
            enabled=True, now=clock, client_factory=server.client, **options
        )

    return make


async def test_the_first_load_gives_ok_data(make_cache, server, clock):
    snapshot = await make_cache().current()
    assert snapshot.state == "ok" and snapshot.detail is None
    assert snapshot.loaded_at == clock.now
    assert snapshot.data is not None and "openrouter" in snapshot.data.providers
    (request,) = server.requests
    assert str(request.url) == MODELS_DEV_URL
    assert set(request.headers) <= HTTPX_DEFAULT_HEADERS
    assert request.headers["user-agent"].startswith("python-httpx/")


async def test_turned_off_sends_nothing():
    def no_client() -> httpx.AsyncClient:
        raise AssertionError("no client may be made")

    cache = ModelsDevCache(enabled=False, client_factory=no_client)
    snapshot = await cache.current()
    assert cache.enabled is False
    assert (snapshot.state, snapshot.detail, snapshot.data) == (
        "unavailable",
        "turned off",
        None,
    )


async def test_fresh_data_sends_no_request(make_cache, server, clock):
    cache = make_cache()
    first = await cache.current()
    clock.advance(hours=5, minutes=59)
    second = await cache.current()
    assert len(server.requests) == 1
    assert second.data is first.data and second.state == "ok"


async def test_stale_data_is_refreshed_with_a_conditional_get(
    make_cache, server, clock
):
    cache = make_cache()
    first = await cache.current()
    clock.advance(hours=6)
    server.reply = reply_status(304)
    unchanged = await cache.current()
    assert server.requests[1].headers["if-none-match"] == "v1"
    assert unchanged.state == "ok" and unchanged.data is first.data
    assert unchanged.loaded_at == clock.now

    clock.advance(hours=6)
    server.reply = ok(OTHER_BODY, "v2")
    changed = await cache.current()
    assert changed.state == "ok" and changed.data is not first.data
    assert changed.data is not None and set(changed.data.providers) == {"openai"}
    clock.advance(hours=6)
    server.reply = reply_status(304)
    await cache.current()
    assert server.requests[3].headers["if-none-match"] == "v2"


async def test_a_load_without_an_etag_sends_no_conditional_header(
    make_cache, server, clock
):
    server.reply = ok(BODY, None)
    cache = make_cache()
    await cache.current()
    clock.advance(hours=6)
    await cache.current()
    assert "if-none-match" not in server.requests[1].headers


@pytest.mark.parametrize(
    "reply,reason",
    [
        (reply_status(503), "HTTP 503"),
        (raise_error(httpx.ReadTimeout("slow")), "timeout after 30 s"),
        (raise_error(httpx.ConnectError("down")), "transport error: ConnectError"),
        (raise_error(RuntimeError("odd")), "fetch failed: RuntimeError"),
        (ok(b"{not json", None), "not valid JSON"),
        (ok(b"[1, 2]", None), "not an object"),
        (ok(b" " * (len(BODY) + 1), None), "body over 0 MiB"),
    ],
)
async def test_each_failure_has_its_reason_and_keeps_the_old_data(
    make_cache, server, clock, reply, reason, caplog
):
    server.reply = reply
    cache = make_cache(max_bytes=len(BODY))
    with caplog.at_level(logging.WARNING):
        empty = await cache.current()
    assert (empty.state, empty.detail, empty.data) == ("unavailable", reason, None)
    assert reason in caplog.text

    server.reply = ok(BODY, "v1")
    clock.advance(minutes=1)
    loaded = await cache.current()
    assert loaded.state == "ok"
    server.reply = reply
    clock.advance(hours=6)
    stale = await cache.current()
    assert (stale.state, stale.detail) == ("stale", reason)
    assert stale.data is loaded.data and stale.loaded_at == loaded.loaded_at


async def test_a_304_without_data_is_a_failure(make_cache, server):
    server.reply = reply_status(304)
    snapshot = await make_cache().current()
    assert (snapshot.state, snapshot.detail) == ("unavailable", "HTTP 304")


async def test_a_slow_trickle_is_cut_by_the_fetch_timeout(make_cache, server):
    server.stalled = True
    cache = make_cache(fetch_timeout_secs=STALL_SECS, wait_secs=5)
    snapshot = await cache.current()
    assert snapshot.detail == f"timeout after {STALL_SECS:g} s"
    server.release()


async def test_no_retry_before_the_interval_without_data(make_cache, server, clock):
    server.reply = reply_status(500)
    cache = make_cache()
    await cache.current()
    clock.advance(seconds=59)
    snapshot = await cache.current()
    assert len(server.requests) == 1 and snapshot.detail == "HTTP 500"
    clock.advance(seconds=1)
    await cache.current()
    assert len(server.requests) == 2


async def test_no_retry_before_the_interval_with_data(make_cache, server, clock):
    cache = make_cache()
    await cache.current()
    server.reply = reply_status(500)
    clock.advance(hours=6)
    await cache.current()
    clock.advance(minutes=9)
    await cache.current()
    assert len(server.requests) == 2
    clock.advance(minutes=1)
    server.reply = reply_status(304)
    snapshot = await cache.current()
    assert len(server.requests) == 3
    assert snapshot.state == "ok" and snapshot.detail is None


async def test_concurrent_calls_make_one_request(make_cache, server):
    cache = make_cache()
    snapshots = await asyncio.gather(*(cache.current() for _ in range(20)))
    assert len(server.requests) == 1
    assert all(s.state == "ok" for s in snapshots)
    assert len({id(s.data) for s in snapshots}) == 1


async def test_a_stalled_first_load_answers_after_the_wait(make_cache, server):
    server.stalled = True
    cache = make_cache(wait_secs=STALL_SECS)
    started = time.monotonic()
    snapshot = await cache.current()
    assert time.monotonic() - started >= STALL_SECS
    assert (snapshot.state, snapshot.detail) == ("unavailable", "loading")
    # A call during the load waits for the same one.
    assert (await cache.current()).detail == "loading"
    assert len(server.requests) == 1
    server.release()
    await cache.settle()
    snapshot = await cache.current()
    assert snapshot.state == "ok" and snapshot.data is not None
    assert len(server.requests) == 1


async def test_a_stalled_refresh_serves_the_stale_data(make_cache, server, clock):
    cache = make_cache(wait_secs=STALL_SECS)
    old = await cache.current()
    clock.advance(hours=6)
    server.stalled = True
    server.reply = ok(OTHER_BODY, "v2")
    snapshot = await cache.current()
    assert (snapshot.state, snapshot.detail) == ("stale", "refresh running")
    assert snapshot.data is old.data
    await cache.current()
    assert len(server.requests) == 2
    server.release()
    await cache.settle()
    snapshot = await cache.current()
    assert snapshot.state == "ok" and snapshot.data is not old.data


async def test_stale_data_inside_the_retry_interval_answers_at_once(
    make_cache, server, clock
):
    cache = make_cache()
    old = await cache.current()
    clock.advance(hours=6)
    server.reply = reply_status(502)
    await cache.current()
    server.stalled = True
    clock.advance(minutes=5)
    snapshot = await asyncio.wait_for(cache.current(), timeout=1)
    assert (snapshot.state, snapshot.detail) == ("stale", "HTTP 502")
    assert snapshot.data is old.data
    assert len(server.requests) == 2


async def test_aclose_cancels_a_running_refresh(make_cache, server):
    server.stalled = True
    cache = make_cache(wait_secs=STALL_SECS)
    await cache.current()
    task = cache._task
    assert task is not None
    await cache.aclose()
    assert task.cancelled()
    snapshot = await cache.current()
    assert snapshot.detail == "not loaded"
    assert len(server.requests) == 1
    await cache.aclose()


async def test_a_load_left_from_another_event_loop_is_ignored(make_cache, server):
    # Starlette's TestClient used without `with` runs each request on a new loop.
    foreign = MagicMock(spec=asyncio.Task)
    foreign.done.return_value = False
    foreign.get_loop.return_value = asyncio.new_event_loop()
    try:
        cache = make_cache()
        cache._task = foreign
        snapshot = await cache.current()
        assert snapshot.state == "ok" and len(server.requests) == 1
        cache._task = foreign
        await cache.settle()
        await cache.aclose()
        foreign.cancel.assert_not_called()
    finally:
        foreign.get_loop.return_value.close()
