import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
    build_llm_as_judge_score,
    score_from_token_string,
)
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import ToolCallContext, ToolCallResult
from kiln_ai.tools.built_in_tools.llm_tools import (
    _DEFAULT_SYSTEM_PROMPT,
    LlmJudgeTool,
    LlmTool,
    run_llm_call,
)

# run_llm_call imports adapter_for_task function-locally from this module, so we
# patch it at its definition site.
ADAPTER_PATH = "kiln_ai.adapters.adapter_registry.adapter_for_task"

VALID_SCORE_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {"score": {"type": "string"}},
        "required": ["score"],
    }
)


def _mock_adapter_for(run_output: RunOutput):
    """Return (factory_mock, adapter_mock) doubling adapter_for_task -> adapter."""
    adapter = AsyncMock()
    adapter.invoke_returning_run_output.return_value = (Mock(), run_output)
    factory = Mock(return_value=adapter)
    return factory, adapter


class TestToolDefinitions:
    async def test_llm_tool_definition(self):
        tool = LlmTool()
        assert await tool.id() == KilnBuiltInToolId.LLM
        assert await tool.name() == "llm"
        defn = await tool.toolcall_definition()
        params = defn["function"]["parameters"]
        assert defn["function"]["name"] == "llm"
        assert params["additionalProperties"] is False
        assert set(params["required"]) == {"prompt", "model", "provider"}
        assert "schema" in params["properties"]

    async def test_llm_judge_tool_definition_has_no_schema_param(self):
        tool = LlmJudgeTool()
        assert await tool.id() == KilnBuiltInToolId.LLM_JUDGE
        assert await tool.name() == "llm_judge"
        defn = await tool.toolcall_definition()
        params = defn["function"]["parameters"]
        assert defn["function"]["name"] == "llm_judge"
        assert params["additionalProperties"] is False
        assert "schema" not in params["properties"]


class TestLlmTool:
    async def test_returns_text_without_schema(self):
        run_output = RunOutput(output="hello world", intermediate_outputs=None)
        factory, adapter = _mock_adapter_for(run_output)

        with patch(ADAPTER_PATH, factory):
            result = await LlmTool().run(
                prompt="Say hi to {{ name }}",
                model="gpt_4o",
                provider="openai",
                input={"name": "Bob"},
            )

        assert isinstance(result, ToolCallResult)
        assert result.output == "hello world"
        adapter.invoke_returning_run_output.assert_awaited_once_with("Say hi to Bob")
        task_arg = factory.call_args[0][0]
        assert task_arg.output_json_schema is None

    async def test_returns_json_string_with_schema(self):
        run_output = RunOutput(output={"rating": "5"}, intermediate_outputs=None)
        factory, _ = _mock_adapter_for(run_output)
        schema = {
            "type": "object",
            "properties": {"rating": {"type": "string"}},
            "required": ["rating"],
        }

        with patch(ADAPTER_PATH, factory):
            result = await LlmTool().run(
                prompt="rate it",
                model="gpt_4o",
                provider="openai",
                schema=schema,
            )

        assert json.loads(result.output) == {"rating": "5"}
        task_arg = factory.call_args[0][0]
        assert task_arg.output_json_schema is not None
        assert "rating" in json.loads(task_arg.output_json_schema)["properties"]

    async def test_system_prompt_passthrough(self):
        run_output = RunOutput(output="ok", intermediate_outputs=None)
        factory, _ = _mock_adapter_for(run_output)

        with patch(ADAPTER_PATH, factory):
            await LlmTool().run(
                prompt="hi",
                model="gpt_4o",
                provider="openai",
                system_prompt="Be terse.",
            )

        task_arg = factory.call_args[0][0]
        assert task_arg.instruction == "Be terse."

    async def test_invalid_schema_raises(self):
        with pytest.raises(ValueError):
            await LlmTool().run(
                prompt="x",
                model="gpt_4o",
                provider="openai",
                schema={"type": "string"},  # not an object schema
            )

    async def test_explicit_empty_schema_is_validated_and_rejected(self):
        # An explicitly-passed {} is not None, so it is validated (and rejected
        # by require_object) rather than silently treated as free-text.
        factory, _ = _mock_adapter_for(RunOutput(output="", intermediate_outputs=None))
        with patch(ADAPTER_PATH, factory):
            with pytest.raises(ValueError):
                await LlmTool().run(
                    prompt="x",
                    model="gpt_4o",
                    provider="openai",
                    schema={},
                )
        factory.assert_not_called()

    async def test_template_syntax_error_raises(self):
        with pytest.raises(ValueError, match="Invalid prompt template"):
            await LlmTool().run(
                prompt="Hi {{ unclosed",
                model="gpt_4o",
                provider="openai",
            )

    async def test_non_ascii_structured_output_preserved(self):
        run_output = RunOutput(
            output={"greeting": "héllo café ☕"}, intermediate_outputs=None
        )
        factory, _ = _mock_adapter_for(run_output)
        schema = {
            "type": "object",
            "properties": {"greeting": {"type": "string"}},
            "required": ["greeting"],
        }

        with patch(ADAPTER_PATH, factory):
            result = await LlmTool().run(
                prompt="hi",
                model="gpt_4o",
                provider="openai",
                schema=schema,
            )

        # ensure_ascii=False keeps literal unicode instead of \uXXXX escapes.
        assert "héllo café ☕" in result.output
        assert "\\u" not in result.output
        assert json.loads(result.output) == {"greeting": "héllo café ☕"}

    async def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="Invalid model provider"):
            await LlmTool().run(
                prompt="hi",
                model="gpt_4o",
                provider="not_a_provider",
            )

    async def test_render_error_raises(self):
        with pytest.raises(ValueError, match="missing data"):
            await LlmTool().run(
                prompt="Hi {{ missing }}",
                model="gpt_4o",
                provider="openai",
                input={},
            )


class TestLlmJudgeTool:
    async def test_off_context_none_raises(self):
        factory, _ = _mock_adapter_for(RunOutput(output={}, intermediate_outputs=None))
        with patch(ADAPTER_PATH, factory):
            with pytest.raises(ValueError, match="only available inside a code judge"):
                await LlmJudgeTool().run(
                    None,
                    prompt="x",
                    model="gpt_4o",
                    provider="openai",
                )
        factory.assert_not_called()

    async def test_off_context_no_schema_raises(self):
        factory, _ = _mock_adapter_for(RunOutput(output={}, intermediate_outputs=None))
        ctx = ToolCallContext()  # eval_output_schema defaults to None
        with patch(ADAPTER_PATH, factory):
            with pytest.raises(ValueError, match="only available inside a code judge"):
                await LlmJudgeTool().run(
                    ctx,
                    prompt="x",
                    model="gpt_4o",
                    provider="openai",
                )
        factory.assert_not_called()

    async def test_maps_pass_fail_critical_and_stars(self):
        run_output = RunOutput(
            output={
                "pass_metric": "pass",
                "fail_metric": "fail",
                "critical_metric": "critical",
                "star_metric": "5",
            },
            intermediate_outputs=None,
        )
        factory, _ = _mock_adapter_for(run_output)
        ctx = ToolCallContext(eval_output_schema=VALID_SCORE_SCHEMA)

        with patch(ADAPTER_PATH, factory):
            result = await LlmJudgeTool().run(
                ctx,
                prompt="judge {{ x }}",
                model="gpt_4o",
                provider="openai",
                input={"x": "y"},
            )

        assert json.loads(result.output) == {
            "pass_metric": 1.0,
            "fail_metric": 0.0,
            "critical_metric": -1.0,
            "star_metric": 5.0,
        }
        # The eval's schema flows through to the judge model call.
        task_arg = factory.call_args[0][0]
        assert task_arg.output_json_schema == VALID_SCORE_SCHEMA

    async def test_parity_with_build_llm_as_judge_score(self):
        output = {"a": "3", "b": "pass", "c": "critical"}
        factory, _ = _mock_adapter_for(
            RunOutput(output=dict(output), intermediate_outputs=None)
        )
        ctx = ToolCallContext(eval_output_schema=VALID_SCORE_SCHEMA)

        with patch(ADAPTER_PATH, factory):
            result = await LlmJudgeTool().run(
                ctx,
                prompt="x",
                model="gpt_4o",
                provider="openai",
            )

        expected = build_llm_as_judge_score(
            RunOutput(output=dict(output), intermediate_outputs=None),
            score_from_token_string,
        )
        assert json.loads(result.output) == expected

    async def test_invalid_provider_raises(self):
        ctx = ToolCallContext(eval_output_schema=VALID_SCORE_SCHEMA)
        with pytest.raises(ValueError, match="Invalid model provider"):
            await LlmJudgeTool().run(
                ctx,
                prompt="hi",
                model="gpt_4o",
                provider="not_a_provider",
            )

    async def test_render_error_raises(self):
        ctx = ToolCallContext(eval_output_schema=VALID_SCORE_SCHEMA)
        with pytest.raises(ValueError, match="missing data"):
            await LlmJudgeTool().run(
                ctx,
                prompt="Hi {{ missing }}",
                model="gpt_4o",
                provider="openai",
            )


class TestRunLlmCall:
    async def test_returns_free_text_run_output(self):
        run_output = RunOutput(output="free text", intermediate_outputs=None)
        factory, adapter = _mock_adapter_for(run_output)

        with patch(ADAPTER_PATH, factory):
            out = await run_llm_call(
                model="gpt_4o",
                provider="openai",
                system_prompt=None,
                rendered_prompt="hi",
                output_json_schema=None,
            )

        assert out is run_output
        assert isinstance(out.output, str)
        adapter.invoke_returning_run_output.assert_awaited_once_with("hi")
        task_arg = factory.call_args[0][0]
        assert task_arg.output_json_schema is None
        # Default system prompt applied when none supplied.
        assert task_arg.instruction == _DEFAULT_SYSTEM_PROMPT

    async def test_returns_structured_run_output(self):
        run_output = RunOutput(output={"k": "v"}, intermediate_outputs=None)
        factory, _ = _mock_adapter_for(run_output)

        with patch(ADAPTER_PATH, factory):
            out = await run_llm_call(
                model="gpt_4o",
                provider="openai",
                system_prompt="custom",
                rendered_prompt="hi",
                output_json_schema=VALID_SCORE_SCHEMA,
            )

        assert out.output == {"k": "v"}
        task_arg = factory.call_args[0][0]
        assert task_arg.output_json_schema == VALID_SCORE_SCHEMA
        assert task_arg.instruction == "custom"

    async def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="Invalid model provider"):
            await run_llm_call(
                model="gpt_4o",
                provider="bogus",
                system_prompt=None,
                rendered_prompt="hi",
                output_json_schema=None,
            )
