"""Tests for agent run context management using contextvars."""

import asyncio

import pytest

from kiln_ai.adapters.adapter_run_context import (
    clear_agent_run_id,
    generate_agent_run_id,
    get_agent_run_id,
    set_agent_run_id,
)


class TestAdapterRunContext:
    """Unit tests for agent run context management."""

    def test_default_is_none(self):
        """Test that the default run ID is None."""
        # Clear any existing context first
        clear_agent_run_id()
        assert get_agent_run_id() is None

    def test_set_and_get(self):
        """Test basic set and get cycle."""
        clear_agent_run_id()
        assert get_agent_run_id() is None

        test_run_id = "test_run_123"
        set_agent_run_id(test_run_id)
        assert get_agent_run_id() == test_run_id

    def test_clear(self):
        """Test that clear resets to None."""
        set_agent_run_id("some_run")
        assert get_agent_run_id() == "some_run"

        clear_agent_run_id()
        assert get_agent_run_id() is None

    def test_generate_agent_run_id_format(self):
        """Test that generated run IDs have the correct format."""
        run_id = generate_agent_run_id()
        assert run_id.startswith("run_")
        assert len(run_id) == 20  # "run_" + 16 hex characters

    def test_generate_agent_run_id_unique(self):
        """Test that generated run IDs are unique."""
        ids = [generate_agent_run_id() for _ in range(100)]
        assert len(set(ids)) == 100  # All should be unique

    @pytest.mark.asyncio
    async def test_asyncio_gather_propagation(self):
        """Test that contextvar propagates through asyncio.gather."""
        clear_agent_run_id()
        parent_run_id = "parent_run"
        set_agent_run_id(parent_run_id)

        child_results = await asyncio.gather(
            self._read_context_var(),
            self._read_context_var(),
            self._read_context_var(),
        )

        # All children should see the parent's run ID
        for result in child_results:
            assert result == parent_run_id

    @pytest.mark.asyncio
    async def test_asyncio_gather_isolation(self):
        """Test that child writes don't affect parent or siblings."""
        clear_agent_run_id()
        parent_run_id = "parent_run"
        set_agent_run_id(parent_run_id)

        async def child_modify_context():
            # Child sets a different value
            set_agent_run_id("child_modified")
            return get_agent_run_id()

        child_results = await asyncio.gather(
            child_modify_context(),
            child_modify_context(),
        )

        # Children should see their own modifications
        for result in child_results:
            assert result == "child_modified"

        # Parent should still have the original value
        assert get_agent_run_id() == parent_run_id

    @pytest.mark.asyncio
    async def test_nested_async_calls_propagate(self):
        """Test that contextvar propagates through nested async calls."""
        clear_agent_run_id()
        root_run_id = "root_run"
        set_agent_run_id(root_run_id)

        async def level_2():
            return get_agent_run_id()

        async def level_1():
            return await level_2()

        result = await level_1()
        assert result == root_run_id

    async def _read_context_var(self) -> str | None:
        """Helper to read the context var in an async context."""
        return get_agent_run_id()
