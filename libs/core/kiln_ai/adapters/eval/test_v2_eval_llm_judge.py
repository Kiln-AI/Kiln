"""Tests for LlmJudgeEval adapter."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from kiln_ai.adapters.eval.v2_eval_llm_judge import (
    _DEFAULT_SYSTEM_PROMPT,
    LlmJudgeEval,
    _LlmJudgeTask,
)
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
    LlmJudgeProperties,
)


def _make_props(**overrides) -> LlmJudgeProperties:
    defaults = {
        "model_name": "gpt-4o",
        "model_provider": "openai",
        "prompt_template": "Rate this: {{ final_message }}",
    }
    defaults.update(overrides)
    return LlmJudgeProperties(**defaults)


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
            thinking_instruction="Think carefully.",
            output_json_schema=_VALID_SCHEMA,
        )
        assert task.instruction == "You are a judge."
        assert task.thinking_instruction == "Think carefully."
        assert task.output_json_schema == _VALID_SCHEMA

    def test_none_thinking_instruction(self):
        task = _LlmJudgeTask(
            system_prompt="Judge it.",
            thinking_instruction=None,
            output_json_schema=_VALID_SCHEMA,
        )
        assert task.thinking_instruction is None


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
            Mock(),
            mock_run_output,
        )
        mock_adapter_for_task.return_value = mock_adapter

        cfg = _make_config()
        scores, skip, detail = await LlmJudgeEval(cfg).evaluate(_inp())

        assert scores == {"quality": 4.0}
        assert skip is None
        assert detail is None

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_pass_fail_scoring(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_run_output = RunOutput(
            output={"quality": "pass"},
            intermediate_outputs=None,
        )
        mock_adapter.invoke_returning_run_output.return_value = (
            Mock(),
            mock_run_output,
        )
        mock_adapter_for_task.return_value = mock_adapter

        cfg = _make_config()
        scores, skip, _ = await LlmJudgeEval(cfg).evaluate(_inp())

        assert scores == {"quality": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_template_rendering(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_run_output = RunOutput(
            output={"quality": "3"},
            intermediate_outputs=None,
        )
        mock_adapter.invoke_returning_run_output.return_value = (
            Mock(),
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
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_custom_system_prompt(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            Mock(),
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
            Mock(),
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
    async def test_thinking_instruction_passed(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            Mock(),
            RunOutput(output={"quality": "5"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(thinking_instruction="Think about quality.")
        cfg = _make_config(props)
        await LlmJudgeEval(cfg).evaluate(_inp())

        task_arg = mock_adapter_for_task.call_args[0][0]
        assert task_arg.thinking_instruction == "Think about quality."

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_adapter_config_llm_as_judge(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            Mock(),
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
        assert adapter_config.forward_thinking_instructions is True

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_invalid_score_raises(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            Mock(),
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
            Mock(),
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
            Mock(),
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
            Mock(),
            RunOutput(output={"quality": "5"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(g_eval=True)
        cfg = _make_config(props)

        with patch(
            "kiln_ai.adapters.eval.v2_eval_llm_judge.build_g_eval_score"
        ) as mock_g_eval_score:
            mock_g_eval_score.return_value = {"quality": 4.3}
            scores, skip, _detail = await LlmJudgeEval(cfg).evaluate(_inp())

        assert scores == {"quality": 4.3}
        assert skip is None

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
            Mock(),
            mock_run_output,
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(g_eval=True)
        cfg = _make_config(props)

        with patch(
            "kiln_ai.adapters.eval.v2_eval_llm_judge.build_g_eval_score"
        ) as mock_g_eval_score:
            mock_g_eval_score.return_value = {"quality": 3.7}
            await LlmJudgeEval(cfg).evaluate(_inp())

        mock_g_eval_score.assert_called_once()
        call_args = mock_g_eval_score.call_args[0]
        assert call_args[0] == mock_run_output


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
            Mock(),
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
            scores, skip, _detail = await LlmJudgeEval(cfg).evaluate(_inp())

        assert scores == {"quality": 4.3}
        assert skip is None

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_g_eval_proceeds_when_provider_unknown(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            Mock(),
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
            scores, skip, _detail = await LlmJudgeEval(cfg).evaluate(_inp())

        assert scores == {"quality": 4.3}
        assert skip is None


class TestLlmJudgeEvalRequiredVars:
    @pytest.mark.asyncio
    async def test_missing_required_var_skips(self):
        props = _make_props(required_var=["reference_data.answer"])
        cfg = _make_config(props)
        scores, skip, detail = await LlmJudgeEval(cfg).evaluate(
            _inp(reference_data=None)
        )
        assert scores == {}
        assert skip is not None
        assert detail is not None

    @pytest.mark.asyncio
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_present_required_var_proceeds(self, mock_adapter_for_task):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            Mock(),
            RunOutput(output={"quality": "3"}, intermediate_outputs=None),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = _make_props(required_var=["reference_data.answer"])
        cfg = _make_config(props)
        scores, skip, _ = await LlmJudgeEval(cfg).evaluate(
            _inp(reference_data={"answer": "correct"})
        )
        assert scores == {"quality": 3.0}
        assert skip is None


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
            Mock(),
            RunOutput(
                output={"quality": "4", "relevance": "pass"},
                intermediate_outputs=None,
            ),
        )
        mock_adapter_for_task.return_value = mock_adapter

        scores, skip, _ = await LlmJudgeEval(cfg).evaluate(_inp())
        assert scores == {"quality": 4.0, "relevance": 1.0}
        assert skip is None
