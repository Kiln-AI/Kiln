import json

import pytest

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.built_in_tools.ask_user_question_tool import (
    ASK_USER_QUESTION_TOOL_NAME,
    AskUserQuestionTool,
)


@pytest.fixture
def tool():
    return AskUserQuestionTool()


class TestAskUserQuestionToolMetadata:
    @pytest.mark.asyncio
    async def test_tool_metadata(self, tool):
        assert await tool.name() == "ask_user_question"
        assert ASK_USER_QUESTION_TOOL_NAME == "ask_user_question"
        assert await tool.id() == KilnBuiltInToolId.ASK_USER_QUESTION
        description = await tool.description()
        assert description
        assert "question" in description.lower()

    @pytest.mark.asyncio
    async def test_toolcall_definition_schema(self, tool):
        definition = await tool.toolcall_definition()
        assert definition["type"] == "function"
        function = definition["function"]
        assert function["name"] == "ask_user_question"
        params = function["parameters"]
        assert params["type"] == "object"

        # `question` is a required string.
        assert params["properties"]["question"]["type"] == "string"
        assert "question" in params["required"]

        # `suggested_answers` is an array capped at 5 items of {answer, explanation}.
        suggested = params["properties"]["suggested_answers"]
        assert suggested["type"] == "array"
        assert suggested["maxItems"] == 5
        items = suggested["items"]
        assert items["type"] == "object"
        assert items["properties"]["answer"]["type"] == "string"
        assert items["properties"]["explanation"]["type"] == "string"
        assert items["required"] == ["answer"]

        # `suggested_answers` is optional (only `question` is required).
        assert params["required"] == ["question"]


class TestAskUserQuestionToolRun:
    """run() is a signal no-op: in chat it is intercepted by name and never
    executed, but it must return a valid asked signal to keep the libs/core
    tool surface complete and standalone."""

    @pytest.mark.asyncio
    async def test_run_returns_asked_signal(self, tool):
        result = await tool.run()
        assert result.is_error is False
        assert json.loads(result.output) == {"status": "asked"}

    @pytest.mark.asyncio
    async def test_run_with_args_is_noop(self, tool):
        # Arbitrary tool args are accepted and ignored by the no-op.
        result = await tool.run(
            question="Which model should I use?",
            suggested_answers=[{"answer": "GPT-4o", "explanation": "Fast and cheap."}],
        )
        assert json.loads(result.output) == {"status": "asked"}

    @pytest.mark.asyncio
    async def test_run_with_positional_context(self, tool):
        # Mirrors LiteLlmAdapter.process_tool_calls: context passed positionally.
        result = await tool.run(ToolCallContext(allow_saving=False))
        assert json.loads(result.output) == {"status": "asked"}

    @pytest.mark.asyncio
    async def test_run_without_context(self, tool):
        # Mirrors studio_server executor: tool.run(**args) with no context.
        result = await tool.run(**{})
        assert json.loads(result.output) == {"status": "asked"}
