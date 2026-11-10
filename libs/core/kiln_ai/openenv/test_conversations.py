"""Tests for the registry that holds OpenEnv sessions between conversation turns. The
session manager is a mock: only which episodes get released matters here."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from kiln_ai.datamodel.openenv import OpenEnvEpisode, OpenEnvReset
from kiln_ai.openenv.conversations import ConversationSessions, HeldSession
from kiln_ai.run_context import EpisodeContext


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def manager():
    m = MagicMock()
    m.release = AsyncMock()
    return m


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
async def sessions(clock):
    registry = ConversationSessions(clock=clock, idle_seconds=100)
    try:
        yield registry
    finally:
        await registry.close_all()


def _held(manager, episode_id="ep_1", loop=None) -> HeldSession:
    openenv_server = MagicMock()
    openenv_server.id = "env-1"
    return HeldSession(
        context=EpisodeContext(
            episode=OpenEnvEpisode(
                reset=OpenEnvReset(openenv_server_id="env-1"),
                episode_id=episode_id,
                openenv_version="acme@1",
            ),
            openenv_server=openenv_server,
            session_manager=manager,
        ),
        loop=loop or asyncio.get_running_loop(),
    )


def _released(manager) -> list[str]:
    return [c.args[0].episode_id for c in manager.release.await_args_list]


class TestTakeAndPut:
    async def test_take_removes_the_entry(self, sessions, manager):
        held = _held(manager)
        sessions.put("turn-1", held)
        assert sessions.take("turn-1") is held
        assert sessions.take("turn-1") is None

    async def test_take_of_an_unknown_turn(self, sessions):
        assert sessions.take("nope") is None

    async def test_session_from_another_loop_is_forgotten(self, sessions, manager):
        other_loop = asyncio.new_event_loop()
        try:
            held = _held(manager, loop=other_loop)
            sessions.put("turn-1", held)
            assert sessions.take("turn-1") is None
            assert not sessions.holds_turn("turn-1")
            assert manager.release.await_count == 0
            manager.forget.assert_called_once_with(held.context.episode)
        finally:
            other_loop.close()

    async def test_peek_forgets_a_session_from_another_loop(self, sessions, manager):
        other_loop = asyncio.new_event_loop()
        try:
            sessions.put("turn-1", _held(manager, loop=other_loop))
            assert sessions.peek("turn-1") is None
            assert sessions.take("turn-1") is None
            manager.forget.assert_called_once()
        finally:
            other_loop.close()

    async def test_peek_leaves_the_entry(self, sessions, manager):
        held = _held(manager)
        sessions.put("turn-1", held)
        assert sessions.peek("turn-1") is held
        assert sessions.peek("other") is None
        assert sessions.take("turn-1") is held

    async def test_put_rekeys_under_the_latest_turn(self, sessions, manager, clock):
        held = _held(manager)
        sessions.put("turn-1", held)
        clock.now += 5
        sessions.put("turn-2", sessions.take("turn-1"))
        assert sessions.take("turn-1") is None
        assert held.turn_run_ids == {"turn-1", "turn-2"}
        assert held.last_used == clock.now
        assert sessions.take("turn-2") is held

    async def test_holds_turn_covers_every_turn_of_a_held_conversation(
        self, sessions, manager
    ):
        held = _held(manager)
        sessions.put("turn-1", held)
        sessions.put("turn-2", sessions.take("turn-1"))
        assert sessions.holds_turn("turn-1")
        assert sessions.holds_turn("turn-2")
        assert not sessions.holds_turn("other")
        sessions.take("turn-2")
        assert not sessions.holds_turn("turn-1")


class TestRelease:
    async def test_release_runs_closes_only_matching_keys(self, sessions, manager):
        sessions.put("turn-a", _held(manager, "ep_a"))
        sessions.put("turn-b", _held(manager, "ep_b"))
        await sessions.release_runs(["turn-a", "unrelated"])
        assert _released(manager) == ["ep_a"]
        assert sessions.take("turn-a") is None
        assert sessions.take("turn-b") is not None

    async def test_release_runs_ignores_earlier_turns(self, sessions, manager):
        sessions.put("turn-1", _held(manager))
        sessions.put("turn-2", sessions.take("turn-1"))
        await sessions.release_runs(["turn-1"])
        assert _released(manager) == []

    async def test_reap_closes_only_idle_sessions(self, sessions, manager, clock):
        sessions.put("old", _held(manager, "ep_old"))
        clock.now += 60
        sessions.put("recent", _held(manager, "ep_recent"))
        clock.now += 60
        await sessions.reap()
        assert _released(manager) == ["ep_old"]
        assert sessions.take("recent") is not None

    async def test_close_all_closes_everything(self, sessions, manager):
        sessions.put("turn-a", _held(manager, "ep_a"))
        sessions.put("turn-b", _held(manager, "ep_b"))
        await sessions.close_all()
        assert sorted(_released(manager)) == ["ep_a", "ep_b"]
        assert not sessions.holds_turn("turn-a")
        assert sessions._reaper is None

    async def test_failed_release_is_logged_not_raised(self, sessions, manager, caplog):
        manager.release.side_effect = RuntimeError("socket gone")
        sessions.put("turn-1", _held(manager))
        with caplog.at_level(logging.WARNING):
            await sessions.release_runs(["turn-1"])
        assert "socket gone" in caplog.text


@pytest.fixture
async def fast_sessions(clock):
    """A registry whose reaper checks every 10 ms."""
    registry = ConversationSessions(
        clock=clock, idle_seconds=100, reap_interval_seconds=0.01
    )
    try:
        yield registry
    finally:
        await registry.close_all()


class TestReaper:
    async def test_reaper_closes_idle_sessions_then_stops(
        self, fast_sessions, manager, clock
    ):
        sessions = fast_sessions
        sessions.put("turn-1", _held(manager))
        reaper = sessions._reaper
        assert reaper is not None
        clock.now += 101
        await asyncio.wait_for(reaper, timeout=5)
        assert _released(manager) == ["ep_1"]
        assert sessions._reaper is None

    async def test_one_reaper_for_many_sessions(self, sessions, manager):
        sessions.put("turn-a", _held(manager, "ep_a"))
        reaper = sessions._reaper
        sessions.put("turn-b", _held(manager, "ep_b"))
        assert sessions._reaper is reaper

    async def test_reaper_survives_a_failed_reap(
        self, fast_sessions, manager, clock, caplog
    ):
        sessions = fast_sessions
        sessions.put("turn-1", _held(manager))
        reaper = sessions._reaper
        assert reaper is not None
        calls = 0
        real_reap = sessions.reap

        async def flaky_reap() -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("disk on fire")
            clock.now += 101
            await real_reap()

        sessions.reap = flaky_reap  # type: ignore[method-assign]
        with caplog.at_level(logging.ERROR):
            await asyncio.wait_for(reaper, timeout=5)
        assert "Couldn't close idle" in caplog.text
        assert _released(manager) == ["ep_1"]
