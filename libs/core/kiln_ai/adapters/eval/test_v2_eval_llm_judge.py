"""Tests for LlmJudgeEval adapter."""

import json
import threading
from unittest.mock import AsyncMock, Mock, patch

import litellm
import pytest
from litellm.types.utils import ModelResponse

from kiln_ai.adapters.chat.chat_formatter import COT_FINAL_ANSWER_PROMPT
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.eval.base_eval import materialize_llm_judge_properties
from kiln_ai.adapters.eval.eval_utils.errors import JudgeContextExceededError
from kiln_ai.adapters.eval.trace_tools import trace_toolset
from kiln_ai.adapters.eval.v2_eval_llm_judge import (
    _DEFAULT_SYSTEM_PROMPT,
    LlmJudgeEval,
    _LlmJudgeTask,
    system_prompt_from_trace,
)
from kiln_ai.adapters.ml_model_list import KilnModelProvider, ModelProviderName
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.test_paid_utils import (
    skip_if_missing_provider_keys,
)
from kiln_ai.adapters.retry_classification import is_retryable_error
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    LATEST_TRACE_TOOLSET_VERSION,
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalOutputScore,
    EvalTaskInput,
    LlmJudgeProperties,
    LlmJudgeRunConfig,
    SkippedReason,
)
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_run import Usage
from kiln_ai.tools.base_tool import ToolCallDefinition
from kiln_ai.utils.config import Config


def _make_props(**overrides) -> LlmJudgeProperties:
    defaults = {
        "model_name": "gpt-4o",
        "model_provider": "openai",
        "prompt_template": "Rate this: {{ final_message }}",
    }
    defaults.update(overrides)
    return LlmJudgeProperties(**defaults)


def _judge_run(
    usage: Usage | None = None, trace: list[dict[str, str]] | None = None
) -> Mock:
    """The judge's own TaskRun, the first half of what the adapter returns.

    Only `usage` and `trace` are read from it. They become `V2EvalResult.usage` and
    `V2EvalResult.judge_trace`, so each must be a real value or None: the result model
    validates them.
    """
    run = Mock()
    run.usage = usage
    run.trace = trace
    return run


def _make_config(props: LlmJudgeProperties | None = None) -> EvalConfig:
    if props is None:
        props = _make_props()
    parent = Mock()
    parent.output_scores = [
        EvalOutputScore(
            name="quality",
            instruction="Rate quality",
            type=TaskOutputRatingType.five_star,
        ),
    ]
    cfg = Mock(spec=EvalConfig)
    cfg.config_type = EvalConfigType.v2
    cfg.properties = props
    cfg.parent_eval.return_value = parent
    cfg.model_name = None
    cfg.model_provider = None
    return cfg


def _inp(**overrides) -> EvalTaskInput:
    defaults: dict = {
        "final_message": "Hello world",
        "trace": None,
        "reference_data": None,
        "task_input": None,
    }
    defaults.update(overrides)
    return EvalTaskInput(**defaults)


class TestLlmJudgeEvalInit:
    def test_valid_construction(self):
        cfg = _make_config()
        adapter = LlmJudgeEval(cfg)
        assert adapter.properties is cfg.properties

    def test_invalid_provider_raises(self):
        props = _make_props(model_provider="not_a_real_provider")
        cfg = _make_config(props)
        with pytest.raises(ValueError, match="Invalid model provider"):
            LlmJudgeEval(cfg)

    def test_non_llm_judge_properties_raises(self):
        cfg = _make_config()
        cfg.properties = "not_properties"
        with pytest.raises(ValueError):
            LlmJudgeEval(cfg)


_VALID_SCHEMA = '{"type": "object", "properties": {"quality": {"type": "string"}}, "required": ["quality"]}'


class TestLlmJudgeTask:
    def test_basic_creation(self):
        task = _LlmJudgeTask(
            system_prompt="You are a judge.",
            output_json_schema=_VALID_SCHEMA,
        )
        assert task.instruction == "You are a judge."
        assert task.output_json_schema == _VALID_SCHEMA


class TestLlmJudgeEvalLlmAsJudge:
    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_basic_scoring(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_run_output = RunOutput(
            output={"quality": "4"},
            intermediate_outputs=None,
        )
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            mock_run_output,
        )
        mock_adapter_for_task.return_value = mock_adapter

        cfg = _make_config()
        result = await LlmJudgeEval(cfg).evaluate(_inp())

        assert result.scores == {"quality": 4.0}
        assert result.skipped_reason is None
        assert result.skipped_detail is None
        assert result.usage is None
        assert result.judge_trace is None

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_judge_usage_is_reported(self, mock_adapter_for_task):
        """What the judgment cost. Nothing recorded it before eval_usage existed."""
        judge_usage = Usage(input_tokens=120, output_tokens=8, cost=0.004)
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(judge_usage),
            RunOutput(output={"quality": "4"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        result = await LlmJudgeEval(_make_config()).evaluate(_inp())

        assert result.usage == judge_usage

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_judge_trace_is_reported(self, mock_adapter_for_task):
        """The judge's conversation, so the rendered prompt can be inspected later."""
        judge_trace = [
            {"role": "system", "content": "Score the output."},
            {"role": "user", "content": "rendered judge prompt"},
            {"role": "assistant", "content": '{"quality": "4"}'},
        ]
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(trace=judge_trace),
            RunOutput(output={"quality": "4"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        result = await LlmJudgeEval(_make_config()).evaluate(_inp())

        assert result.judge_trace == judge_trace

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_intermediate_outputs_propagated(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_run_output = RunOutput(
            output={"quality": "4"},
            intermediate_outputs={
                "chain_of_thought": "The answer is correct because it addresses all key points."
            },
        )
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            mock_run_output,
        )
        mock_adapter_for_task.return_value = mock_adapter

        cfg = _make_config()
        result = await LlmJudgeEval(cfg).evaluate(_inp())

        assert result.scores == {"quality": 4.0}
        assert result.intermediate_outputs == {
            "chain_of_thought": "The answer is correct because it addresses all key points."
        }

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_pass_fail_scoring(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_run_output = RunOutput(
            output={"quality": "pass"},
            intermediate_outputs=None,
        )
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            mock_run_output,
        )
        mock_adapter_for_task.return_value = mock_adapter

        cfg = _make_config()
        result = await LlmJudgeEval(cfg).evaluate(_inp())

        assert result.scores == {"quality": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_template_rendering(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_run_output = RunOutput(
            output={"quality": "3"},
            intermediate_outputs=None,
        )
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            mock_run_output,
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(
            prompt_template="Input: {{ task_input }}, Output: {{ final_message }}"
        )
        cfg = _make_config(props)
        await LlmJudgeEval(cfg).evaluate(
            _inp(final_message="answer", task_input="question")
        )

        call_args = mock_adapter.invoke_returning_run_output.call_args
        rendered = call_args[0][0]
        assert "Input: question" in rendered
        assert "Output: answer" in rendered

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "trace, expected",
        [
            (
                [
                    {"role": "system", "content": "Be terse."},
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "Hello world"},
                ],
                "System: [Be terse.]",
            ),
            ([{"role": "user", "content": "hi"}], "System: []"),
            (None, "System: []"),
        ],
        ids=["system-message", "no-system-message", "no-trace"],
    )
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_system_prompt_variable(self, mock_adapter_for_task, trace, expected):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "3"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(
            prompt_template="System: [{{ system_prompt }}] Output: {{ final_message }}"
        )
        result = await LlmJudgeEval(_make_config(props)).evaluate(_inp(trace=trace))

        assert result.skipped_reason is None
        rendered = mock_adapter.invoke_returning_run_output.call_args[0][0]
        assert rendered.startswith(expected)

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_custom_system_prompt(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "5"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(system_prompt="Custom instructions here.")
        cfg = _make_config(props)
        await LlmJudgeEval(cfg).evaluate(_inp())

        task_arg = mock_adapter_for_task.call_args[0][0]
        assert task_arg.instruction == "Custom instructions here."

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_default_system_prompt(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "5"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(system_prompt=None)
        cfg = _make_config(props)
        await LlmJudgeEval(cfg).evaluate(_inp())

        task_arg = mock_adapter_for_task.call_args[0][0]
        assert task_arg.instruction == _DEFAULT_SYSTEM_PROMPT

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_adapter_config_llm_as_judge(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "5"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(g_eval=False)
        cfg = _make_config(props)
        await LlmJudgeEval(cfg).evaluate(_inp())

        call_kwargs = mock_adapter_for_task.call_args[1]
        adapter_config = call_kwargs["base_adapter_config"]
        assert adapter_config.allow_saving is False
        assert adapter_config.top_logprobs is None

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_invalid_score_raises(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "garbage"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        cfg = _make_config()
        with pytest.raises(ValueError, match="No score found for metric"):
            await LlmJudgeEval(cfg).evaluate(_inp())

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_non_dict_output_raises(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output="just a string", intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        cfg = _make_config()
        with pytest.raises(ValueError, match="must be a dictionary"):
            await LlmJudgeEval(cfg).evaluate(_inp())

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.BaseEval.build_score_schema")
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_discrete_score_schema(
        self, mock_adapter_for_task, mock_build_schema
    ):
        mock_build_schema.return_value = _VALID_SCHEMA
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "3"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        cfg = _make_config()
        await LlmJudgeEval(cfg).evaluate(_inp())

        discrete_calls = [
            c
            for c in mock_build_schema.call_args_list
            if c[1].get("allow_float_scores") is False
        ]
        assert len(discrete_calls) == 1


class TestLlmJudgeEvalGEval:
    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_adapter_config_g_eval(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "5"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(g_eval=True)
        cfg = _make_config(props)

        with (
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.built_in_models_from_provider",
                return_value=Mock(supports_logprobs=True),
            ),
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.build_g_eval_score"
            ) as mock_g_eval_score,
        ):
            mock_g_eval_score.return_value = {"quality": 4.3}
            result = await LlmJudgeEval(cfg).evaluate(_inp())

        assert result.scores == {"quality": 4.3}
        assert result.skipped_reason is None

        call_kwargs = mock_adapter_for_task.call_args[1]
        adapter_config = call_kwargs["base_adapter_config"]
        assert adapter_config.top_logprobs == 10

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_g_eval_calls_scoring_functions(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_run_output = RunOutput(
            output={"quality": "5"},
            intermediate_outputs=None,
        )
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            mock_run_output,
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(g_eval=True)
        cfg = _make_config(props)

        with (
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.built_in_models_from_provider",
                return_value=Mock(supports_logprobs=True),
            ),
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.build_g_eval_score"
            ) as mock_g_eval_score,
        ):
            mock_g_eval_score.return_value = {"quality": 3.7}
            await LlmJudgeEval(cfg).evaluate(_inp())

        mock_g_eval_score.assert_called_once()
        call_args = mock_g_eval_score.call_args[0]
        assert call_args[0] == mock_run_output

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_g_eval_judge_trace_is_reported(self, mock_adapter_for_task):
        judge_trace = [
            {"role": "system", "content": "Score the output."},
            {"role": "user", "content": "rendered judge prompt"},
            {"role": "assistant", "content": '{"quality": "5"}'},
        ]
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(trace=judge_trace),
            RunOutput(output={"quality": "5"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        with (
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.built_in_models_from_provider",
                return_value=Mock(supports_logprobs=True),
            ),
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.build_g_eval_score",
                return_value={"quality": 4.3},
            ),
        ):
            result = await LlmJudgeEval(
                _make_config(_make_props(g_eval=True))
            ).evaluate(_inp())

        assert result.scores == {"quality": 4.3}
        assert result.judge_trace == judge_trace


class TestLlmJudgeEvalGEvalFailFast:
    @pytest.mark.asyncio
    async def test_g_eval_raises_when_provider_lacks_logprobs(self):
        mock_provider = Mock()
        mock_provider.supports_logprobs = False
        props = _make_props(g_eval=True)
        cfg = _make_config(props)
        adapter = LlmJudgeEval(cfg)

        with patch(
            "kiln_ai.adapters.eval.v2_eval_llm_judge.built_in_models_from_provider",
            return_value=mock_provider,
        ):
            with pytest.raises(ValueError, match="logprobs support"):
                await adapter.evaluate(_inp())

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_g_eval_proceeds_when_provider_supports_logprobs(
        self, mock_adapter_for_task
    ):
        mock_provider = Mock()
        mock_provider.supports_logprobs = True

        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "5"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(g_eval=True)
        cfg = _make_config(props)

        with (
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.built_in_models_from_provider",
                return_value=mock_provider,
            ),
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.build_g_eval_score"
            ) as mock_g_eval_score,
        ):
            mock_g_eval_score.return_value = {"quality": 4.3}
            result = await LlmJudgeEval(cfg).evaluate(_inp())

        assert result.scores == {"quality": 4.3}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_g_eval_proceeds_when_provider_unknown(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "5"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(g_eval=True)
        cfg = _make_config(props)

        with (
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.built_in_models_from_provider",
                return_value=None,
            ),
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.build_g_eval_score"
            ) as mock_g_eval_score,
        ):
            mock_g_eval_score.return_value = {"quality": 4.3}
            result = await LlmJudgeEval(cfg).evaluate(_inp())

        assert result.scores == {"quality": 4.3}
        assert result.skipped_reason is None


class TestLlmJudgeEvalMissingReferenceData:
    @pytest.mark.asyncio
    async def test_undefined_reference_key_skips_cleanly(self):
        props = _make_props(
            prompt_template="Answer: {{ reference_data.answer }} Output: {{ final_message }}"
        )
        cfg = _make_config(props)
        result = await LlmJudgeEval(cfg).evaluate(_inp(reference_data=None))
        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.missing_reference_key
        assert result.skipped_detail is not None
        assert "missing data" in result.skipped_detail.lower()

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_present_reference_data_proceeds(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "3"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(
            prompt_template="Answer: {{ reference_data.answer }} Output: {{ final_message }}"
        )
        cfg = _make_config(props)
        result = await LlmJudgeEval(cfg).evaluate(
            _inp(reference_data={"answer": "correct"})
        )
        assert result.scores == {"quality": 3.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_unknown_template_variable_is_extraction_failure(self):
        # A typo'd variable is a template-authoring bug, not missing reference
        # data -- it must not masquerade as missing_reference_key.
        props = _make_props(prompt_template="Output: {{ final_mesage }}")
        cfg = _make_config(props)
        result = await LlmJudgeEval(cfg).evaluate(_inp())
        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.extraction_failed
        assert result.skipped_detail is not None
        assert "unknown variable" in result.skipped_detail
        assert "final_mesage" in result.skipped_detail

    @pytest.mark.asyncio
    async def test_typo_alongside_reference_access_reports_unknown_variable(self):
        # When the template has both a typo and a missing reference key, the
        # authoring bug is the primary truth to surface.
        props = _make_props(
            prompt_template="{{ reference_data.answer }} vs {{ outpt }}"
        )
        cfg = _make_config(props)
        result = await LlmJudgeEval(cfg).evaluate(_inp(reference_data=None))
        assert result.skipped_reason == SkippedReason.extraction_failed
        assert result.skipped_detail is not None
        assert "outpt" in result.skipped_detail


class TestLlmJudgeEvalDeclaredReferenceKeys:
    """`reference_keys` is a declared requirement: a judge that cannot get one skips
    loudly instead of scoring against ground truth it never saw."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "reference_data, expected_detail",
        [
            (None, "No reference_data"),
            ({"other": "x"}, "missing key 'reference_answer'"),
            ({"reference_answer": None}, "key 'reference_answer' is None"),
        ],
        ids=["no-reference-data", "wrong-key", "null-value"],
    )
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_missing_declared_key_skips_without_calling_the_model(
        self, mock_adapter_for_task, reference_data, expected_detail
    ):
        props = _make_props(reference_keys=["reference_answer"])
        cfg = _make_config(props)

        result = await LlmJudgeEval(cfg).evaluate(_inp(reference_data=reference_data))

        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.missing_reference_key
        assert result.skipped_detail is not None
        assert expected_detail in result.skipped_detail
        mock_adapter_for_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_skips_on_the_first_unsatisfied_key(self, mock_adapter_for_task):
        props = _make_props(reference_keys=["reference_answer", "retrieved_context"])
        cfg = _make_config(props)

        result = await LlmJudgeEval(cfg).evaluate(
            _inp(reference_data={"reference_answer": "Frank Herbert."})
        )

        assert result.skipped_reason == SkippedReason.missing_reference_key
        assert result.skipped_detail is not None
        assert "retrieved_context" in result.skipped_detail
        mock_adapter_for_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_satisfied_keys_score_normally(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "5"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(
            reference_keys=["reference_answer"],
            prompt_template=(
                "Reference: {{ reference_data.reference_answer }} "
                "Output: {{ final_message }}"
            ),
        )
        cfg = _make_config(props)

        result = await LlmJudgeEval(cfg).evaluate(
            _inp(reference_data={"reference_answer": "Frank Herbert."})
        )

        assert result.scores == {"quality": 5.0}
        assert result.skipped_reason is None
        rendered = mock_adapter.invoke_returning_run_output.call_args[0][0]
        assert "Frank Herbert." in rendered

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_no_declared_keys_does_not_require_reference_data(
        self, mock_adapter_for_task
    ):
        """A judge that declares nothing is not required to have anything: the
        requirement is the declaration, not the presence of reference data."""
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "2"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        cfg = _make_config(_make_props())
        result = await LlmJudgeEval(cfg).evaluate(_inp(reference_data=None))

        assert result.scores == {"quality": 2.0}
        assert result.skipped_reason is None


class TestBackendBakedReferenceAnswerJudge:
    """The declared-key guard is only worth having if a shipped path reaches it.
    `materialize_llm_judge_properties` is that path: it bakes both the prompt block and
    the declaration for a reference-answer eval, so these tests use the real properties
    rather than hand-written ones."""

    @staticmethod
    def _baked_props() -> LlmJudgeProperties:
        task = Task(name="QnA Task", instruction="Answer questions about the docs")
        eval_obj = Eval(
            name="Reference Answer Eval",
            evaluation_data_type=EvalDataType.reference_answer,
            output_scores=[
                EvalOutputScore(
                    name="quality",
                    instruction="Rate quality",
                    type=TaskOutputRatingType.five_star,
                )
            ],
            eval_set_filter_id="tag::test",
            parent=task,
        )
        return materialize_llm_judge_properties(
            eval_obj, "gpt-4o", "openai", g_eval=False
        )

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_item_without_a_reference_skips_before_the_model_call(
        self, mock_adapter_for_task
    ):
        """Judge calibration scores the golden item as itself, so it supplies no
        reference data by design — every calibration item of such a judge skips. That
        is the right answer for "does this match the reference" with no reference, and
        it costs no inference."""
        cfg = _make_config(self._baked_props())

        result = await LlmJudgeEval(cfg).evaluate(_inp(reference_data=None))

        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.missing_reference_key
        mock_adapter_for_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_the_reference_reaches_the_rendered_prompt(
        self, mock_adapter_for_task
    ):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "5"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter
        cfg = _make_config(self._baked_props())

        result = await LlmJudgeEval(cfg).evaluate(
            _inp(
                final_message="Herbert, 1965.",
                task_input="Who wrote Dune?",
                trace=[
                    {"role": "user", "content": "Who wrote Dune?"},
                    {"role": "assistant", "content": "Herbert, 1965."},
                ],
                reference_data={"reference_answer": "Frank Herbert."},
            )
        )

        assert result.skipped_reason is None
        rendered = mock_adapter.invoke_returning_run_output.call_args[0][0]
        assert "<reference_answer>\nFrank Herbert.\n</reference_answer>" in rendered

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_item_without_a_trace_skips_before_the_model_call(
        self, mock_adapter_for_task
    ):
        """The default prompt is built on the trace, so an item without one has
        nothing for the judge to read and is skipped rather than scored blind."""
        mock_adapter_for_task.return_value = AsyncMock()
        cfg = _make_config(self._baked_props())

        result = await LlmJudgeEval(cfg).evaluate(
            _inp(trace=None, reference_data={"reference_answer": "Frank Herbert."})
        )

        assert result.skipped_reason == SkippedReason.extraction_failed
        mock_adapter_for_task.return_value.invoke_returning_run_output.assert_not_called()


class TestLlmJudgeEvalNoParentEval:
    def test_no_parent_eval_raises(self):
        cfg = _make_config()
        cfg.parent_eval.return_value = None
        with pytest.raises(ValueError, match="parent eval"):
            LlmJudgeEval(cfg)


class TestLlmJudgeEvalMultipleScores:
    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_multiple_metrics(self, mock_adapter_for_task):
        parent = Mock()
        parent.output_scores = [
            EvalOutputScore(
                name="quality",
                instruction="Rate quality",
                type=TaskOutputRatingType.five_star,
            ),
            EvalOutputScore(
                name="relevance",
                instruction="Rate relevance",
                type=TaskOutputRatingType.pass_fail,
            ),
        ]
        cfg = _make_config()
        cfg.parent_eval.return_value = parent

        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(
                output={"quality": "4", "relevance": "pass"},
                intermediate_outputs=None,
            ),
        )
        mock_adapter_for_task.return_value = mock_adapter

        result = await LlmJudgeEval(cfg).evaluate(_inp())
        assert result.scores == {"quality": 4.0, "relevance": 1.0}
        assert result.skipped_reason is None


class TestLlmJudgeEvalTemplateRenderError:
    @pytest.mark.asyncio
    async def test_fromjson_on_non_json_skips_cleanly(self):
        props = _make_props(
            prompt_template="Result: {{ (final_message | fromjson).status }}"
        )
        cfg = _make_config(props)
        result = await LlmJudgeEval(cfg).evaluate(_inp(final_message="not valid json"))
        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.extraction_failed
        assert result.skipped_detail is not None
        assert "not valid JSON" in result.skipped_detail


class TestLlmJudgeE2EMessageConstruction:
    """End-to-end test exercising the REAL adapter/chat-formatter pipeline.

    Mocks only at the model boundary (litellm.acompletion) to verify that
    the messages sent to the LLM are exactly the rendered prompt (no
    <user_input> wrapping, no appended 'Think step by step' instruction)
    and the system message equals the configured system_prompt.

    g_eval variant omitted: logprob mocking is non-trivial; g_eval scoring
    is covered by existing unit tests and shares the same message path.
    """

    _SYSTEM_PROMPT = "You are an expert code reviewer. Be strict."
    _PROMPT_TEMPLATE = (
        "Task: {{ task_input }}\n"
        "Response: {{ final_message }}\n"
        "Trace: {{ trace | tojson }}\n"
        "Ref: {{ reference_data.expected_answer }}"
    )
    _TASK_INPUT = "Implement a binary search function."
    _FINAL_MESSAGE = "def binary_search(arr, target): ..."

    @staticmethod
    def _trace() -> list[dict[str, str]]:
        return [
            {"role": "user", "content": "Implement binary search"},
            {"role": "assistant", "content": "def binary_search(arr, target): ..."},
        ]

    @staticmethod
    def _reference_data() -> dict[str, str]:
        return {"expected_answer": "A correct O(log n) implementation"}

    def _build_config(self) -> EvalConfig:
        props = LlmJudgeProperties(
            model_name="gpt-4o",
            model_provider="openai",
            prompt_template=self._PROMPT_TEMPLATE,
            system_prompt=self._SYSTEM_PROMPT,
        )
        parent = Mock()
        parent.output_scores = [
            EvalOutputScore(
                name="quality",
                instruction="Rate quality",
                type=TaskOutputRatingType.five_star,
            ),
            EvalOutputScore(
                name="correctness",
                instruction="Is the answer correct?",
                type=TaskOutputRatingType.pass_fail,
            ),
        ]
        cfg = Mock(spec=EvalConfig)
        cfg.config_type = EvalConfigType.v2
        cfg.properties = props
        cfg.parent_eval.return_value = parent
        cfg.model_name = None
        cfg.model_provider = None
        return cfg

    def _build_input(self) -> EvalTaskInput:
        return EvalTaskInput(
            task_input=self._TASK_INPUT,
            final_message=self._FINAL_MESSAGE,
            trace=self._trace(),
            reference_data=self._reference_data(),
        )

    def _expected_user_message(self) -> str:
        trace_json = json.dumps(self._trace(), sort_keys=True)
        ref = self._reference_data()
        return (
            f"Task: {self._TASK_INPUT}\n"
            f"Response: {self._FINAL_MESSAGE}\n"
            f"Trace: {trace_json}\n"
            f"Ref: {ref['expected_answer']}"
        )

    @pytest.mark.asyncio
    async def test_llm_as_judge_messages_sent_verbatim(self):
        """The user message must be the rendered prompt verbatim — no wrapping."""
        model_response = ModelResponse(
            model="gpt-4o",
            choices=[
                {
                    "message": {
                        "content": json.dumps({"quality": 4, "correctness": "pass"}),
                    }
                }
            ],
        )

        captured_kwargs: list[dict] = []

        async def fake_acompletion(**kwargs):
            captured_kwargs.append(kwargs)
            return model_response

        mock_config_obj = Mock()
        mock_config_obj.open_ai_api_key = "fake-key"
        mock_config_obj.user_id = "test_user"

        cfg = self._build_config()
        eval_input = self._build_input()

        with (
            patch("litellm.acompletion", side_effect=fake_acompletion),
            patch(
                "kiln_ai.utils.config.Config.shared",
                return_value=mock_config_obj,
            ),
        ):
            result = await LlmJudgeEval(cfg).evaluate(eval_input)

        assert len(captured_kwargs) == 1
        messages = captured_kwargs[0]["messages"]

        system_msgs = [m for m in messages if m["role"] == "system"]
        user_msgs = [m for m in messages if m["role"] == "user"]

        assert len(system_msgs) == 1
        assert len(user_msgs) == 1

        system_content = system_msgs[0]["content"]
        user_content = user_msgs[0]["content"]

        assert system_content == self._SYSTEM_PROMPT
        assert user_content == self._expected_user_message()

        assert "The input is:" not in user_content
        assert "<user_input>" not in user_content
        assert "Think step by step" not in user_content

        assert result.scores == {"quality": 4.0, "correctness": 1.0}
        assert result.skipped_reason is None


class TestLlmJudgeRunConfig:
    """The judge's optional run_config. Unset (or any unset field in it) must keep the
    default, so older configs behave as before; a set field must reach the model call;
    an unknown thinking level must fail rather than be sent or silently dropped."""

    @staticmethod
    def _mock_adapter(mock_adapter_for_task) -> None:
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(output={"quality": "4"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

    @staticmethod
    def _run_config_properties(mock_adapter_for_task) -> KilnAgentRunConfigProperties:
        return mock_adapter_for_task.call_args.kwargs["run_config_properties"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("run_config", [None, LlmJudgeRunConfig()])
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_unset_keeps_defaults(self, mock_adapter_for_task, run_config):
        self._mock_adapter(mock_adapter_for_task)
        props = _make_props(
            model_name="gpt_5_6_terra",
            model_provider="openrouter",
            run_config=run_config,
        )
        await LlmJudgeEval(_make_config(props)).evaluate(_inp())

        rc = self._run_config_properties(mock_adapter_for_task)
        for field in ("thinking_level", "temperature", "top_p"):
            assert field not in rc.model_fields_set
        assert rc.thinking_level is None
        assert rc.temperature == 1.0
        assert rc.top_p == 1.0

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_set_fields_reach_the_model_call(self, mock_adapter_for_task):
        self._mock_adapter(mock_adapter_for_task)
        props = _make_props(
            model_name="gpt_5_6_terra",
            model_provider="openrouter",
            run_config=LlmJudgeRunConfig(
                thinking_level="medium", temperature=0.2, top_p=0.9
            ),
        )
        await LlmJudgeEval(_make_config(props)).evaluate(_inp())

        rc = self._run_config_properties(mock_adapter_for_task)
        assert {"thinking_level", "temperature", "top_p"} <= rc.model_fields_set
        assert rc.thinking_level == "medium"
        assert rc.temperature == 0.2
        assert rc.top_p == 0.9

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_partial_run_config_keeps_other_defaults(self, mock_adapter_for_task):
        self._mock_adapter(mock_adapter_for_task)
        props = _make_props(run_config=LlmJudgeRunConfig(temperature=0.0))
        await LlmJudgeEval(_make_config(props)).evaluate(_inp())

        rc = self._run_config_properties(mock_adapter_for_task)
        assert rc.temperature == 0.0
        assert "thinking_level" not in rc.model_fields_set
        assert rc.top_p == 1.0

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_unknown_level_raises(self, mock_adapter_for_task):
        self._mock_adapter(mock_adapter_for_task)
        props = _make_props(
            model_name="gpt_5_6_terra",
            model_provider="openrouter",
            run_config=LlmJudgeRunConfig(thinking_level="ultra"),
        )
        with pytest.raises(ValueError, match="not available"):
            await LlmJudgeEval(_make_config(props)).evaluate(_inp())
        mock_adapter_for_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_level_on_model_without_levels_raises(self, mock_adapter_for_task):
        self._mock_adapter(mock_adapter_for_task)
        props = _make_props(
            model_name="gpt_4o",
            model_provider="openai",
            run_config=LlmJudgeRunConfig(thinking_level="low"),
        )
        with pytest.raises(ValueError, match="has no thinking levels"):
            await LlmJudgeEval(_make_config(props)).evaluate(_inp())
        mock_adapter_for_task.assert_not_called()

    def test_run_config_validation(self):
        with pytest.raises(ValueError, match="non-empty"):
            LlmJudgeRunConfig(thinking_level="  ")
        assert LlmJudgeRunConfig(thinking_level=" low ").thinking_level == "low"
        with pytest.raises(ValueError):
            LlmJudgeRunConfig(temperature=2.5)
        with pytest.raises(ValueError):
            LlmJudgeRunConfig(top_p=-0.1)

    def test_older_config_without_run_config_loads(self):
        props = LlmJudgeProperties.model_validate(
            {
                "model_name": "gpt-4o",
                "model_provider": "openai",
                "prompt_template": "Rate this",
            }
        )
        assert props.run_config is None

    @staticmethod
    def _materialize(**kwargs) -> LlmJudgeProperties:
        with (
            patch(
                "kiln_ai.adapters.eval.base_eval.build_default_llm_judge_prompt",
                return_value="prompt",
            ),
            patch(
                "kiln_ai.adapters.eval.base_eval.derived_reference_keys",
                return_value=[],
            ),
        ):
            return materialize_llm_judge_properties(
                eval=Mock(),
                model_name="gpt_5_6_terra",
                model_provider="openrouter",
                g_eval=False,
                **kwargs,
            )

    def test_materialize_carries_run_config(self):
        run_config = LlmJudgeRunConfig(thinking_level="low", temperature=0.5)
        assert self._materialize(run_config=run_config).run_config == run_config
        assert self._materialize().run_config is None

    def test_materialize_rejects_unknown_level(self):
        with pytest.raises(ValueError, match="not available"):
            self._materialize(run_config=LlmJudgeRunConfig(thinking_level="ultra"))


class TestSystemPromptFromTrace:
    def test_reads_text_parts_of_list_content(self):
        trace = [
            {"role": "system", "content": [{"type": "text", "text": "Be terse."}]},
        ]
        assert system_prompt_from_trace(trace) == "Be terse."

    def test_returns_first_system_message(self):
        trace = [
            {"role": "system", "content": "first"},
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "second"},
        ]
        assert system_prompt_from_trace(trace) == "first"

    @pytest.mark.parametrize(
        "trace",
        [None, [], [{"role": "user", "content": "hi"}], [{"role": "system"}]],
        ids=["none", "empty", "no-system", "no-content"],
    )
    def test_empty_when_absent(self, trace):
        assert system_prompt_from_trace(trace) == ""


_JUDGED_TRACE = [
    {"role": "system", "content": "You are a librarian."},
    {"role": "user", "content": "Who wrote Dune?"},
    {"role": "assistant", "content": "Frank Herbert, in 1965."},
]


def _v1_overview(trace: list[dict[str, str]]) -> str:
    toolset = trace_toolset(1)
    return toolset.render_overview(toolset.build_view(trace))


def _scoring_adapter(trace: list[dict[str, str]] | None = None) -> AsyncMock:
    adapter = AsyncMock()
    adapter.invoke_returning_run_output.return_value = (
        _judge_run(trace=trace),
        RunOutput(output={"quality": "4"}, intermediate_outputs=None),
    )
    return adapter


class _RecordingToolset:
    """A stand-in trace toolset that records which thread did its CPU work."""

    def __init__(self, version: int):
        self.version = version
        self.threads: list[int] = []

    def build_view(self, trace):
        self.threads.append(threading.get_ident())
        return ("view", self.version)

    def render_overview(self, view) -> str:
        self.threads.append(threading.get_ident())
        return f"overview v{view[1]}"

    def build_tools(self, view):
        return []

    @property
    def judge_thinking_instruction(self) -> str:
        return f"investigate v{self.version}"


class TestLlmJudgeTraceTools:
    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_trace_tools_on_passes_the_five_tools_and_caches(
        self, mock_adapter_for_task
    ):
        judge_trace = [{"role": "assistant", "content": '{"quality": "4"}'}]
        mock_adapter_for_task.return_value = _scoring_adapter(judge_trace)
        cfg = _make_config(
            _make_props(prompt_template="Judge it.", trace_toolset_version=1)
        )

        result = await LlmJudgeEval(cfg).evaluate(_inp(trace=_JUDGED_TRACE))

        adapter_config = mock_adapter_for_task.call_args[1]["base_adapter_config"]
        assert adapter_config.automatic_prompt_caching is True
        assert adapter_config.unmanaged_tools is not None
        assert [await tool.name() for tool in adapter_config.unmanaged_tools] == [
            "trace_overview",
            "preview_messages",
            "read_messages",
            "read_message_text",
            "search_trace",
        ]
        assert result.scores == {"quality": 4.0}
        assert result.judge_trace == judge_trace

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_trace_tools_off_passes_no_tools(self, mock_adapter_for_task):
        mock_adapter_for_task.return_value = _scoring_adapter()

        await LlmJudgeEval(_make_config()).evaluate(_inp(trace=_JUDGED_TRACE))

        adapter_config = mock_adapter_for_task.call_args[1]["base_adapter_config"]
        assert adapter_config.unmanaged_tools is None
        assert adapter_config.automatic_prompt_caching is False

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_trace_tools_judge_answers_in_a_separate_turn(
        self, mock_adapter_for_task
    ):
        mock_adapter_for_task.return_value = _scoring_adapter()
        toolset = _RecordingToolset(2)
        cfg = _make_config(_make_props(trace_toolset_version=2))

        with patch(
            "kiln_ai.adapters.eval.v2_eval_llm_judge.trace_toolset",
            return_value=toolset,
        ):
            await LlmJudgeEval(cfg).evaluate(_inp(trace=_JUDGED_TRACE))

        judge_task = mock_adapter_for_task.call_args[0][0]
        kwargs = mock_adapter_for_task.call_args[1]
        assert judge_task.thinking_instruction == toolset.judge_thinking_instruction
        assert (
            kwargs["run_config_properties"].prompt_id
            == PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT
        )
        assert kwargs["base_adapter_config"].separate_final_answer_turn is True

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_judge_without_trace_tools_answers_in_one_turn(
        self, mock_adapter_for_task
    ):
        mock_adapter_for_task.return_value = _scoring_adapter()

        await LlmJudgeEval(_make_config()).evaluate(_inp(trace=_JUDGED_TRACE))

        judge_task = mock_adapter_for_task.call_args[0][0]
        kwargs = mock_adapter_for_task.call_args[1]
        assert judge_task.thinking_instruction is None
        assert kwargs["run_config_properties"].prompt_id == PromptGenerators.SIMPLE
        assert kwargs["base_adapter_config"].separate_final_answer_turn is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "trace_toolset_version, expected",
        [
            (1, {"chain_of_thought": "Findings."}),
            (None, {"chain_of_thought": "Findings.", "reasoning": "Format it."}),
        ],
    )
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_trace_tools_judge_reports_its_findings_as_reasoning(
        self, mock_adapter_for_task, trace_toolset_version, expected
    ):
        adapter = AsyncMock()
        adapter.invoke_returning_run_output.return_value = (
            _judge_run(),
            RunOutput(
                output={"quality": "4"},
                intermediate_outputs={
                    "chain_of_thought": "Findings.",
                    "reasoning": "Format it.",
                },
            ),
        )
        mock_adapter_for_task.return_value = adapter
        cfg = _make_config(_make_props(trace_toolset_version=trace_toolset_version))

        result = await LlmJudgeEval(cfg).evaluate(_inp(trace=_JUDGED_TRACE))

        assert result.intermediate_outputs == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("trace", [None, []])
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_trace_tools_without_a_trace_skips(
        self, mock_adapter_for_task, trace
    ):
        cfg = _make_config(_make_props(trace_toolset_version=1))

        result = await LlmJudgeEval(cfg).evaluate(_inp(trace=trace))

        assert result.skipped_reason == SkippedReason.missing_trace
        assert result.skipped_detail is not None
        mock_adapter_for_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_trace_overview_renders_in_a_tools_off_template(
        self, mock_adapter_for_task
    ):
        mock_adapter = _scoring_adapter()
        mock_adapter_for_task.return_value = mock_adapter
        cfg = _make_config(
            _make_props(prompt_template="<o>{{ trace | trace_overview }}</o>")
        )

        await LlmJudgeEval(cfg).evaluate(_inp(trace=_JUDGED_TRACE))

        rendered = mock_adapter.invoke_returning_run_output.call_args[0][0]
        assert rendered == f"<o>{_v1_overview(_JUDGED_TRACE)}</o>"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "trace_toolset_version, expected_overview",
        [(2, "overview v2"), (None, "overview v1")],
    )
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_trace_overview_follows_the_judge_version(
        self, mock_adapter_for_task, trace_toolset_version, expected_overview
    ):
        """A judge with trace tools renders its own version's overview; one without
        them always renders the v1 overview, so its prompt never changes."""
        mock_adapter = _scoring_adapter()
        mock_adapter_for_task.return_value = mock_adapter
        cfg = _make_config(
            _make_props(
                prompt_template="{{ trace | trace_overview }}",
                trace_toolset_version=trace_toolset_version,
            )
        )

        with patch(
            "kiln_ai.adapters.eval.v2_eval_llm_judge.trace_toolset",
            side_effect=lambda version: _RecordingToolset(version),
        ):
            await LlmJudgeEval(cfg).evaluate(_inp(trace=_JUDGED_TRACE))

        rendered = mock_adapter.invoke_returning_run_output.call_args[0][0]
        assert rendered == expected_overview

    def test_unsupported_trace_toolset_version_refuses_to_build(self):
        """Fails when the judge is built, not as a skip from evaluate(): a skip is
        saved as a final result, and the item would never run after an update."""
        cfg = _make_config(_make_props(trace_toolset_version=99))

        with pytest.raises(ValueError) as e:
            LlmJudgeEval(cfg)

        assert str(e.value) == (
            "This judge uses trace tools version 99, which this version of Kiln "
            "doesn't support. Update Kiln to run it."
        )
        assert not is_retryable_error(e.value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("trace_toolset_version", [1, None])
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_view_and_render_run_off_the_event_loop(
        self, mock_adapter_for_task, trace_toolset_version
    ):
        """Parsing a large trace is CPU-bound. With tools on the view is built up
        front; with tools off the overview filter builds it during the render.
        Neither may run on the event loop's thread."""
        mock_adapter_for_task.return_value = _scoring_adapter()
        cfg = _make_config(
            _make_props(
                prompt_template="{{ trace | trace_overview }}",
                trace_toolset_version=trace_toolset_version,
            )
        )
        toolset = _RecordingToolset(1)

        with patch(
            "kiln_ai.adapters.eval.v2_eval_llm_judge.trace_toolset",
            return_value=toolset,
        ):
            await LlmJudgeEval(cfg).evaluate(_inp(trace=_JUDGED_TRACE))

        assert len(toolset.threads) == 2
        assert threading.get_ident() not in toolset.threads


def _run_error(original: Exception, tool_messages: int = 0) -> KilnRunError:
    partial_trace = [{"role": "user", "content": "rendered judge prompt"}] + [
        {"role": "tool", "tool_call_id": f"call_{i}", "content": "tool output"}
        for i in range(tool_messages)
    ]
    return KilnRunError(
        message="The judge failed.", partial_trace=partial_trace, original=original
    )


class TestLlmJudgeContextExceeded:
    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_context_window_overflow_is_not_retried(self, mock_adapter_for_task):
        overflow = litellm.ContextWindowExceededError(
            message="too long", model="gpt-4o", llm_provider="openai"
        )
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.side_effect = _run_error(
            overflow, tool_messages=2
        )
        mock_adapter_for_task.return_value = mock_adapter
        cfg = _make_config(_make_props(trace_toolset_version=1))

        with pytest.raises(JudgeContextExceededError) as exc_info:
            await LlmJudgeEval(cfg).evaluate(_inp(trace=_JUDGED_TRACE))

        assert exc_info.value.tool_call_count == 2
        assert "after 2 trace tool calls" in str(exc_info.value)
        assert is_retryable_error(exc_info.value) is False

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_other_run_errors_propagate_unchanged(self, mock_adapter_for_task):
        run_error = _run_error(RuntimeError("Too many tool calls"))
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.side_effect = run_error
        mock_adapter_for_task.return_value = mock_adapter

        with pytest.raises(KilnRunError) as exc_info:
            await LlmJudgeEval(_make_config()).evaluate(_inp())

        assert exc_info.value is run_error

    @pytest.mark.parametrize(
        "tool_call_count, expected",
        [
            (
                1234,
                "The judge model ran out of context after 1,234 trace tool calls. Use "
                "a judge model with a larger context window, or a prompt that needs "
                "less of the trace.",
            ),
            (
                1,
                "The judge model ran out of context after 1 trace tool call. Use "
                "a judge model with a larger context window, or a prompt that needs "
                "less of the trace.",
            ),
            (
                0,
                "The judge model ran out of context. Use a judge model with a larger "
                "context window, or a prompt that needs less of the trace.",
            ),
        ],
    )
    def test_message(self, tool_call_count, expected):
        assert str(JudgeContextExceededError(tool_call_count)) == expected

    def test_from_run_error_counts_tool_results(self):
        error = JudgeContextExceededError.from_run_error(
            _run_error(ValueError("overflow"), tool_messages=3)
        )
        assert error.tool_call_count == 3


class TestLlmJudgeTraceToolsEndToEnd:
    """The real adapter loop with a scripted model: in its first turn the judge reads
    the trace with a tool and describes its decision; in the final turn it gives its
    scores."""

    _FINDINGS = "The answer matches the trace. I'd rate it 4."

    @classmethod
    def _model_turns(cls) -> list[ModelResponse]:
        tool_call = {
            "id": "call_overview",
            "type": "function",
            "function": {"name": "trace_overview", "arguments": "{}"},
        }
        return [
            ModelResponse(
                model="gpt-4o",
                choices=[{"message": {"content": None, "tool_calls": [tool_call]}}],
            ),
            ModelResponse(
                model="gpt-4o",
                choices=[{"message": {"content": cls._FINDINGS}}],
            ),
            ModelResponse(
                model="gpt-4o",
                choices=[
                    {
                        "message": {
                            "content": json.dumps({"quality": 4}),
                            "reasoning_content": "Now format the scores.",
                        }
                    }
                ],
            ),
        ]

    @pytest.mark.asyncio
    async def test_judge_reads_the_trace_then_scores_in_a_final_turn(self):
        Config.shared().save_setting("open_ai_api_key", "fake-key")
        turns = self._model_turns()
        cfg = _make_config(
            _make_props(prompt_template="Judge the trace.", trace_toolset_version=1)
        )
        build_completion_kwargs = AsyncMock(return_value={})

        with (
            # A reasoning model would answer in one turn on the usual chain of thought
            # path; a trace tools judge still gets its separate final turn.
            patch.object(
                LiteLlmAdapter,
                "model_provider",
                return_value=KilnModelProvider(
                    name=ModelProviderName.openai,
                    model_id="gpt-4o",
                    reasoning_capable=True,
                ),
            ),
            patch.object(
                LiteLlmAdapter, "build_completion_kwargs", build_completion_kwargs
            ),
            patch.object(
                LiteLlmAdapter,
                "acompletion_checking_response",
                side_effect=[(turn, turn.choices[0]) for turn in turns],
            ),
        ):
            result = await LlmJudgeEval(cfg).evaluate(_inp(trace=_JUDGED_TRACE))

        assert result.scores == {"quality": 4.0}
        assert result.intermediate_outputs == {"chain_of_thought": self._FINDINGS}
        skip_response_format = [
            call.args[3] for call in build_completion_kwargs.call_args_list
        ]
        assert skip_response_format == [True, True, False]

        assert result.judge_trace is not None
        assert [m["role"] for m in result.judge_trace] == [
            "system",
            "user",
            "assistant",
            "tool",
            "assistant",
            "user",
            "assistant",
        ]
        _, prompt, _, tool_result, findings, final_request, answer = result.judge_trace
        assert prompt["content"] == (
            f"Judge the trace.\n\n{trace_toolset(1).judge_thinking_instruction}"
        )
        assert tool_result["content"] == _v1_overview(_JUDGED_TRACE)
        assert findings["content"] == self._FINDINGS
        assert final_request["content"] == COT_FINAL_ANSWER_PROMPT
        assert answer["content"] == json.dumps({"quality": 4})
        assert answer.get("reasoning_content") == "Now format the scores."


_ORDER_LOOKUP_ANSWER = (
    "Good news! Order A1234 is on schedule with UPS and will arrive tomorrow, "
    "October 18."
)
_ORDER_LOOKUP_TRACE = [
    {
        "role": "system",
        "content": (
            "You are a support agent for an online store. Look up orders with the "
            "lookup_order tool before answering questions about them."
        ),
    },
    {"role": "user", "content": "Where is my order A1234, and when will it arrive?"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_lookup",
                "type": "function",
                "function": {
                    "name": "lookup_order",
                    "arguments": '{"order_id": "A1234"}',
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_lookup",
        "content": json.dumps(
            {
                "order_id": "A1234",
                "status": "delayed",
                "carrier": "UPS",
                "estimated_delivery": "2026-10-31",
                "note": "Held at the regional depot after a storm.",
            }
        ),
    },
    {"role": "assistant", "content": _ORDER_LOOKUP_ANSWER},
]

# Cheap judges from four vendor families. Between them they cover each structured
# output mode the judge sends alongside its tools: json_schema,
# json_instruction_and_object and json_instructions.
_AGENTIC_JUDGE_LIVE_MODELS = [
    "claude_haiku_5_5",
    "gemini_3_8_flash",
    "qwen_3p8_flash",
    "glm_5_3_flash",
]


class TestAgenticJudgeLive:
    """An agentic judge on real models through OpenRouter.

    The trace overview in the judge's prompt previews the question and the final
    answer, but not the tool result the answer contradicts, so the judge has to read
    the trace with its tools to score it. Run these alone with:

        uv run python3 -m pytest -n0 -v --runpaid \\
            "libs/core/kiln_ai/adapters/eval/test_v2_eval_llm_judge.py::TestAgenticJudgeLive"
    """

    @staticmethod
    def _judge_config(model_name: str) -> EvalConfig:
        eval = Eval(
            name="Order Answers",
            parent=Task(
                name="Order Support", instruction="Answer questions about orders."
            ),
            eval_set_filter_id="tag::eval_set",
            evaluation_data_type=EvalDataType.full_trace,
            output_scores=[
                EvalOutputScore(
                    name="Matches Order Data",
                    instruction=(
                        "Does the final answer give the order status and delivery "
                        "date that the order lookup returned?"
                    ),
                    type=TaskOutputRatingType.pass_fail,
                ),
                EvalOutputScore(
                    name="Overall Rating",
                    instruction="Rate the final answer overall.",
                    type=TaskOutputRatingType.five_star,
                ),
            ],
        )
        return EvalConfig(
            name="Agentic Judge",
            parent=eval,
            config_type=EvalConfigType.v2,
            properties=materialize_llm_judge_properties(
                eval,
                model_name,
                ModelProviderName.openrouter.value,
                g_eval=False,
                judge_instructions=[
                    "Compare the final answer with what the order lookup tool returned."
                ],
                trace_tools=True,
            ),
        )

    @staticmethod
    async def _trace_tool_definitions() -> list[ToolCallDefinition]:
        toolset = trace_toolset(LATEST_TRACE_TOOLSET_VERSION)
        tools = toolset.build_tools(toolset.build_view(_ORDER_LOOKUP_TRACE))
        return [await tool.toolcall_definition() for tool in tools]

    @pytest.mark.paid
    @pytest.mark.asyncio
    @pytest.mark.parametrize("model_name", _AGENTIC_JUDGE_LIVE_MODELS)
    async def test_judge_reads_the_trace_then_scores(self, model_name: str):
        skip_if_missing_provider_keys(ModelProviderName.openrouter)
        definitions = await self._trace_tool_definitions()
        trace_tool_names = {
            definition["function"]["name"] for definition in definitions
        }
        assert any(
            "maximum" in parameter
            for definition in definitions
            for parameter in definition["function"]["parameters"]["properties"].values()
        ), "a pass should also show the provider accepts numeric bounds in tool schemas"

        result = await LlmJudgeEval(self._judge_config(model_name)).evaluate(
            EvalTaskInput(
                final_message=_ORDER_LOOKUP_ANSWER,
                trace=_ORDER_LOOKUP_TRACE,
            )
        )

        assert result.skipped_reason is None, result.skipped_detail
        assert result.judge_trace is not None
        *before_answer, answer = result.judge_trace
        assert answer["role"] == "assistant" and not answer.get("tool_calls")
        called = [
            call["function"]["name"]
            for message in before_answer
            if message["role"] == "assistant"
            for call in message.get("tool_calls") or []
        ]
        assert trace_tool_names & set(called), (
            f"{model_name} answered without calling a trace tool; it called {called}"
        )
        tool_results = [m for m in before_answer if m["role"] == "tool"]
        assert any(not m.get("is_error") for m in tool_results), (
            f"every trace tool call by {model_name} failed: {tool_results}"
        )

        assert set(result.scores) == {"matches_order_data", "overall_rating"}
        assert result.scores["matches_order_data"] in (0.0, 1.0)
        overall = result.scores["overall_rating"]
        assert 1.0 <= overall <= 5.0 and overall == int(overall)
        # The answer plainly contradicts the lookup result, so a pass means the tool
        # output didn't reach the judge intact.
        assert result.scores["matches_order_data"] == 0.0, result.intermediate_outputs
