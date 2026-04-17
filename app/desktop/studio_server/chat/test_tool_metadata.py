from app.desktop.studio_server.chat import tool_input_executor_is_server
from app.desktop.studio_server.chat.tool_metadata import tool_requires_user_approval
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent


class TestToolRequiresUserApproval:
    def test_tool_requires_user_approval_accepts_bool_metadata(self):
        ev = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="x",
            toolName="t",
            input={},
            kiln_metadata={"requires_approval": True},
        )
        assert tool_requires_user_approval(ev) is True
        ev2 = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="x",
            toolName="t",
            input={},
            kiln_metadata={"requires_approval": False},
        )
        assert tool_requires_user_approval(ev2) is False

    def test_tool_requires_user_approval_rejects_non_bool_requires_approval(self):
        ev = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="x",
            toolName="t",
            input={},
            kiln_metadata={"requires_approval": "true"},
        )
        assert tool_requires_user_approval(ev) is False

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
        assert tool_requires_user_approval(ev) is True


class TestToolInputExecutorServer:
    def test_executor_server_is_true(self):
        event = ToolInputAvailableEvent(
            toolCallId="tc1",
            toolName="some_tool",
            input={},
            kiln_metadata={"executor": "server"},
        )
        assert tool_input_executor_is_server(event) is True

    def test_executor_absent_or_other_is_false(self):
        assert (
            tool_input_executor_is_server(
                ToolInputAvailableEvent(
                    toolCallId="tc1",
                    toolName="some_tool",
                    input={},
                )
            )
            is False
        )
        assert (
            tool_input_executor_is_server(
                ToolInputAvailableEvent(
                    toolCallId="tc1",
                    toolName="some_tool",
                    input={},
                    kiln_metadata={"executor": "client"},
                )
            )
            is False
        )
