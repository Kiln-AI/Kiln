import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from kiln_ai.tools.mcp_session_cache import CachedSession, MCPSessionCache


@pytest.fixture
def cache():
    return MCPSessionCache()


def create_cached_session(
    session_close_side_effect=None, context_close_side_effect=None
):
    """Create a CachedSession with mock session and context."""
    session = Mock()
    session.__aexit__ = AsyncMock(side_effect=session_close_side_effect)

    context = Mock()
    context.__aexit__ = AsyncMock(side_effect=context_close_side_effect)
    return CachedSession(session=session, context=context)


@pytest.mark.asyncio
async def test_cache_initialization(cache):
    """Test that cache initializes empty."""
    assert await cache.get("any-id") is None


@pytest.mark.asyncio
async def test_set_and_get(cache):
    """Test storing and retrieving a session."""
    cached_session = create_cached_session()
    await cache.set("test-server-1", cached_session)
    assert await cache.get("test-server-1") is cached_session.session


@pytest.mark.asyncio
async def test_set_multiple_sessions(cache):
    """Test storing multiple sessions."""
    cached_session1 = create_cached_session()
    cached_session2 = create_cached_session()

    await cache.set("server-1", cached_session1)
    await cache.set("server-2", cached_session2)

    assert await cache.get("server-1") is cached_session1.session
    assert await cache.get("server-2") is cached_session2.session


@pytest.mark.asyncio
async def test_set_overwrites_existing(cache):
    """Test that setting a session with same ID overwrites and closes old session."""
    server_id = "test-server"
    cached_session1 = create_cached_session()
    cached_session2 = create_cached_session()

    await cache.set(server_id, cached_session1)
    await cache.set(server_id, cached_session2)

    assert await cache.get(server_id) is cached_session2.session
    # Old context should be closed to prevent memory leak
    cached_session1.context.__aexit__.assert_called_once_with(None, None, None)


@pytest.mark.asyncio
async def test_close_session(cache):
    """Test closing a specific session."""
    cached_session = create_cached_session()
    server_id = "test-server"

    await cache.set(server_id, cached_session)
    await cache.close_session(server_id)

    assert await cache.get(server_id) is None
    cached_session.context.__aexit__.assert_called_once_with(None, None, None)


@pytest.mark.asyncio
async def test_close_session_ignores_errors(cache):
    """Test that close_session ignores errors during cleanup."""
    cached_session = create_cached_session(
        context_close_side_effect=Exception("Close failed")
    )

    server_id = "test-server"
    await cache.set(server_id, cached_session)

    # Should not raise
    await cache.close_session(server_id)

    assert await cache.get(server_id) is None
    cached_session.context.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_close_all(cache):
    """Test closing all sessions."""
    cached_session1 = create_cached_session()
    cached_session2 = create_cached_session()

    await cache.set("server-1", cached_session1)
    await cache.set("server-2", cached_session2)

    await cache.close_all()

    assert await cache.get("server-1") is None
    assert await cache.get("server-2") is None
    cached_session1.context.__aexit__.assert_called_once()
    cached_session2.context.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_close_session_nonexistent(cache):
    """Test closing a session that doesn't exist does nothing."""
    # Should not raise
    await cache.close_session("nonexistent")


@pytest.mark.asyncio
async def test_concurrent_operations_no_race_condition(cache):
    """Test that concurrent operations don't cause race condition."""

    async def mixed_operations(i: int):
        # Mix of get, set, and close operations
        cached_session = create_cached_session()
        await cache.set(f"server-{i}", cached_session)
        retrieved = await cache.get(f"server-{i}")
        assert retrieved is cached_session.session
        return cached_session.session

    # Launch concurrent operations 10 times
    tasks = [mixed_operations(i) for i in range(10)]
    sessions = await asyncio.gather(*tasks)

    # Verify final state is consistent
    for i, session in enumerate(sessions):
        assert await cache.get(f"server-{i}") is session
