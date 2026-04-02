import asyncio

import pytest
from app.desktop.studio_server.chat import (
    _register_tool_approval_wait,
    _tool_requires_user_approval,
    submit_tool_approval_decisions,
)
from fastapi import HTTPException
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent


class TestToolApprovalHelpers:
    def test_tool_requires_user_approval_accepts_bool_metadata(self):
        ev = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="x",
            toolName="t",
            input={},
            kiln_metadata={"requires_approval": True},
        )
        assert _tool_requires_user_approval(ev) is True
        ev2 = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="x",
            toolName="t",
            input={},
            kiln_metadata={"requires_approval": False},
        )
        assert _tool_requires_user_approval(ev2) is False

    def test_tool_requires_user_approval_rejects_non_bool_requires_approval(self):
        ev = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="x",
            toolName="t",
            input={},
            kiln_metadata={"requires_approval": "true"},
        )
        assert _tool_requires_user_approval(ev) is False

    def test_kiln_metadata_extra_keys_do_not_break_parsing(self):
        ev = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="x",
            toolName="t",
            input={},
            kiln_metadata={
                "requires_approval": True,
                "future_flag": 1,
            },
        )
        assert _tool_requires_user_approval(ev) is True

    def test_submit_tool_approval_resolves_registered_future(self):
        async def run() -> None:
            fut = await _register_tool_approval_wait("batch-unit-1", frozenset({"tc1"}))
            await submit_tool_approval_decisions("batch-unit-1", {"tc1": True})
            assert await fut == {"tc1": True}

        asyncio.run(run())

    def test_submit_tool_approval_unknown_batch_404(self):
        async def run() -> None:
            with pytest.raises(HTTPException) as ei:
                await submit_tool_approval_decisions(
                    "00000000-0000-0000-0000-000000000099", {"tc1": True}
                )
            assert ei.value.status_code == 404

        asyncio.run(run())

    def test_post_tool_approval_unknown_batch_http(self, client, mock_api_key):
        r = client.post(
            "/api/chat/tool-approval",
            json={
                "approval_batch_id": "00000000-0000-0000-0000-000000000088",
                "decisions": {"tc1": True},
            },
        )
        assert r.status_code == 404
