import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from kiln_ai.tools.mcp_session_cache import MCPSessionCache


@pytest.fixture
def cache():
    return MCPSessionCache()


def create_mock_session(close_side_effect=None):
    """Create a mock ClientSession with optional close error."""
    session = Mock()
    session.__aexit__ = AsyncMock(side_effect=close_side_effect)
    return session


@pytest.mark.asyncio
async def test_cache_initialization(cache):
    """Test that cache initializes empty."""
    assert await cache.get("any-id") is None


@pytest.mark.asyncio
async def test_set_and_get(cache):
    """Test storing and retrieving a session."""
    session = create_mock_session()
    await cache.set("test-server-1", session)
    assert await cache.get("test-server-1") is session


@pytest.mark.asyncio
async def test_set_multiple_sessions(cache):
    """Test storing multiple sessions."""
    session1 = create_mock_session()
    session2 = create_mock_session()

    await cache.set("server-1", session1)
    await cache.set("server-2", session2)

    assert await cache.get("server-1") is session1
    assert await cache.get("server-2") is session2


@pytest.mark.asyncio
async def test_set_overwrites_existing(cache):
    """Test that setting a session with same ID overwrites and closes old session."""
    server_id = "test-server"
    session1 = create_mock_session()
    session2 = create_mock_session()

    await cache.set(server_id, session1)
    await cache.set(server_id, session2)

    assert await cache.get(server_id) is session2
    # Old session should be closed to prevent memory leak
    session1.__aexit__.assert_called_once_with(None, None, None)


@pytest.mark.asyncio
async def test_close_session(cache):
    """Test closing a specific session."""
    session = create_mock_session()
    server_id = "test-server"

    await cache.set(server_id, session)
    await cache.close_session(server_id)

    assert await cache.get(server_id) is None
    session.__aexit__.assert_called_once_with(None, None, None)


@pytest.mark.asyncio
async def test_close_session_ignores_errors(cache):
    """Test that close_session ignores errors during cleanup."""
    session = create_mock_session(Exception("Close failed"))

    server_id = "test-server"
    await cache.set(server_id, session)

    # Should not raise
    await cache.close_session(server_id)

    assert await cache.get(server_id) is None
    session.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_close_all(cache):
    """Test closing all sessions."""
    session1 = create_mock_session()
    session2 = create_mock_session()

    await cache.set("server-1", session1)
    await cache.set("server-2", session2)

    await cache.close_all()

    assert await cache.get("server-1") is None
    assert await cache.get("server-2") is None
    session1.__aexit__.assert_called_once()
    session2.__aexit__.assert_called_once()


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
        session = create_mock_session()
        await cache.set(f"server-{i}", session)
        retrieved = await cache.get(f"server-{i}")
        assert retrieved is session
        return session

    # Launch concurrent operations 10 times
    tasks = [mixed_operations(i) for i in range(10)]
    sessions = await asyncio.gather(*tasks)

    # Verify final state is consistent
    for i, session in enumerate(sessions):
        assert await cache.get(f"server-{i}") is session
