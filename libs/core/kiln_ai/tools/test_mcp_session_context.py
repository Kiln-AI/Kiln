"""Tests for MCP session context management using contextvars."""

import asyncio

import pytest

from kiln_ai.tools.mcp_session_context import (
    clear_mcp_session_id,
    generate_session_id,
    get_mcp_session_id,
    set_mcp_session_id,
)


class TestMcpSessionContext:
    """Unit tests for MCP session context management."""

    def test_default_is_none(self):
        """Test that the default session ID is None."""
        # Clear any existing context first
        clear_mcp_session_id()
        assert get_mcp_session_id() is None

    def test_set_and_get(self):
        """Test basic set and get cycle."""
        clear_mcp_session_id()
        assert get_mcp_session_id() is None

        test_session_id = "test_session_123"
        set_mcp_session_id(test_session_id)
        assert get_mcp_session_id() == test_session_id

    def test_clear(self):
        """Test that clear resets to None."""
        set_mcp_session_id("some_session")
        assert get_mcp_session_id() == "some_session"

        clear_mcp_session_id()
        assert get_mcp_session_id() is None

    def test_generate_session_id_format(self):
        """Test that generated session IDs have the correct format."""
        session_id = generate_session_id()
        assert session_id.startswith("mcp_")
        assert len(session_id) == 20  # "mcp_" + 16 hex characters

    def test_generate_session_id_unique(self):
        """Test that generated session IDs are unique."""
        ids = [generate_session_id() for _ in range(100)]
        assert len(set(ids)) == 100  # All should be unique

    @pytest.mark.asyncio
    async def test_asyncio_gather_propagation(self):
        """Test that contextvar propagates through asyncio.gather."""
        clear_mcp_session_id()
        parent_session_id = "parent_session"
        set_mcp_session_id(parent_session_id)

        child_results = await asyncio.gather(
            self._read_context_var(),
            self._read_context_var(),
            self._read_context_var(),
        )

        # All children should see the parent's session ID
        for result in child_results:
            assert result == parent_session_id

    @pytest.mark.asyncio
    async def test_asyncio_gather_isolation(self):
        """Test that child writes don't affect parent or siblings."""
        clear_mcp_session_id()
        parent_session_id = "parent_session"
        set_mcp_session_id(parent_session_id)

        async def child_modify_context():
            # Child sets a different value
            set_mcp_session_id("child_modified")
            return get_mcp_session_id()

        child_results = await asyncio.gather(
            child_modify_context(),
            child_modify_context(),
        )

        # Children should see their own modifications
        for result in child_results:
            assert result == "child_modified"

        # Parent should still have the original value
        assert get_mcp_session_id() == parent_session_id

    @pytest.mark.asyncio
    async def test_nested_async_calls_propagate(self):
        """Test that contextvar propagates through nested async calls."""
        clear_mcp_session_id()
        root_session_id = "root_session"
        set_mcp_session_id(root_session_id)

        async def level_2():
            return get_mcp_session_id()

        async def level_1():
            return await level_2()

        result = await level_1()
        assert result == root_session_id

    async def _read_context_var(self) -> str | None:
        """Helper to read the context var in an async context."""
        return get_mcp_session_id()
