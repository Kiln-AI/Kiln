"""Tests for RAG judge template factory functions."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import check_required_vars
from kiln_ai.adapters.eval.rag_judge_templates import (
    answer_correctness_template,
    answer_relevance_template,
    context_precision_template,
    context_relevance_template,
    faithfulness_template,
    hallucination_template,
)
from kiln_ai.adapters.eval.v2_eval_llm_judge import LlmJudgeEval
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
    LlmJudgeProperties,
    SkippedReason,
)
from kiln_ai.datamodel.task import Task
from kiln_ai.utils.jinja_engine import compile_template_or_raise

_MODEL = "gpt-4o"
_PROVIDER = "openai"

_ALL_FACTORIES = [
    faithfulness_template,
    answer_relevance_template,
    context_relevance_template,
    context_precision_template,
    hallucination_template,
    answer_correctness_template,
]


class TestRagTemplateProperties:
    def test_faithfulness_template(self):
        props = faithfulness_template(_MODEL, _PROVIDER)
        assert isinstance(props, LlmJudgeProperties)
        assert props.model_name == _MODEL
        assert props.model_provider == _PROVIDER
        assert props.required_var == ["reference_data.retrieved_context"]
        assert (
            "{% for chunk in reference_data.retrieved_context %}"
            in props.prompt_template
        )
        assert "{{ final_message }}" in props.prompt_template
        assert props.thinking_instruction is not None
        assert props.system_prompt is not None
        assert props.g_eval is False

    def test_answer_relevance_template(self):
        props = answer_relevance_template(_MODEL, _PROVIDER)
        assert isinstance(props, LlmJudgeProperties)
        assert props.required_var == ["task_input"]
        assert "{{ task_input }}" in props.prompt_template
        assert "{{ final_message }}" in props.prompt_template
        assert props.thinking_instruction is not None
        assert props.g_eval is False

    def test_context_relevance_template(self):
        props = context_relevance_template(_MODEL, _PROVIDER)
        assert isinstance(props, LlmJudgeProperties)
        assert "task_input" in props.required_var
        assert "reference_data.retrieved_context" in props.required_var
        assert "{{ task_input }}" in props.prompt_template
        assert (
            "{% for chunk in reference_data.retrieved_context %}"
            in props.prompt_template
        )
        assert props.g_eval is False

    def test_context_precision_template(self):
        props = context_precision_template(_MODEL, _PROVIDER)
        assert isinstance(props, LlmJudgeProperties)
        assert "task_input" in props.required_var
        assert "reference_data.retrieved_context" in props.required_var
        assert "{{ task_input }}" in props.prompt_template
        assert (
            "{% for chunk in reference_data.retrieved_context %}"
            in props.prompt_template
        )
        assert "{% if reference_data.ground_truth_context %}" in props.prompt_template
        assert props.g_eval is False

    def test_hallucination_template(self):
        props = hallucination_template(_MODEL, _PROVIDER)
        assert isinstance(props, LlmJudgeProperties)
        assert props.required_var == ["reference_data.retrieved_context"]
        assert (
            "{% for chunk in reference_data.retrieved_context %}"
            in props.prompt_template
        )
        assert "{{ final_message }}" in props.prompt_template
        assert props.g_eval is False

    def test_answer_correctness_template(self):
        props = answer_correctness_template(_MODEL, _PROVIDER)
        assert isinstance(props, LlmJudgeProperties)
        assert "reference_data.reference_answer" in props.required_var
        assert "task_input" in props.required_var
        assert "{{ reference_data.reference_answer }}" in props.prompt_template
        assert "{{ final_message }}" in props.prompt_template
        assert props.g_eval is False


class TestRagTemplateCompilation:
    @pytest.mark.parametrize("factory", _ALL_FACTORIES, ids=lambda f: f.__name__)
    def test_template_compiles(self, factory):
        props = factory(_MODEL, _PROVIDER)
        compile_template_or_raise(props.prompt_template)

    @pytest.mark.parametrize("factory", _ALL_FACTORIES, ids=lambda f: f.__name__)
    def test_template_not_useless(self, factory):
        props = factory(_MODEL, _PROVIDER)
        tmpl = props.prompt_template.strip()
        assert "{{" in tmpl or "{%" in tmpl, (
            f"{factory.__name__} template has no Jinja expressions or blocks"
        )


class TestRagTemplateEvalConfig:
    @pytest.mark.parametrize("factory", _ALL_FACTORIES, ids=lambda f: f.__name__)
    def test_eval_config_validates(self, factory, tmp_path):
        props = factory(_MODEL, _PROVIDER)

        task = Task(
            name="test_task",
            instruction="Do the thing.",
            path=tmp_path / "task.kiln",
        )
        task.save_to_file()

        eval_obj = Eval(
            name="test_eval",
            eval_input_filter_id="all",
            eval_configs_filter_id="all",
            output_scores=[
                EvalOutputScore(
                    name="score",
                    instruction="Rate it.",
                    type=TaskOutputRatingType.pass_fail,
                ),
            ],
            parent=task,
        )
        eval_obj.save_to_file()

        config = EvalConfig(
            name="rag_config",
            config_type=EvalConfigType.v2,
            properties=props,
            parent=eval_obj,
        )
        assert config.config_type == EvalConfigType.v2
        assert isinstance(config.properties, LlmJudgeProperties)


class TestRagTemplateScoringSmoke:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "factory",
        [faithfulness_template, answer_relevance_template],
        ids=["faithfulness", "answer_relevance"],
    )
    @patch("kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task")
    async def test_llm_as_judge_returns_float_score(
        self, mock_adapter_for_task, factory
    ):
        mock_adapter = AsyncMock()
        mock_adapter.invoke_returning_run_output.return_value = (
            Mock(),
            RunOutput(
                output={
                    "claims": [{"claim": "X", "supported": True}],
                    "num_supported": 1,
                    "num_total": 1,
                    "score": 0.85,
                    "reasoning": "Good.",
                },
                intermediate_outputs=None,
            ),
        )
        mock_adapter_for_task.return_value = mock_adapter

        props = factory(_MODEL, _PROVIDER)
        parent_eval = Mock()
        parent_eval.output_scores = [
            EvalOutputScore(
                name="score",
                instruction="Rate it.",
                type=TaskOutputRatingType.pass_fail,
            ),
        ]

        cfg = Mock(spec=EvalConfig)
        cfg.config_type = EvalConfigType.v2
        cfg.properties = props
        cfg.parent_eval.return_value = parent_eval
        cfg.model_name = None
        cfg.model_provider = None

        eval_input = EvalTaskInput(
            final_message="Paris is the capital of France.",
            task_input="What is the capital of France?",
            reference_data={
                "retrieved_context": ["France's capital is Paris."],
                "reference_answer": "Paris",
            },
        )

        scores, skip, _detail = await LlmJudgeEval(cfg).evaluate(eval_input)
        assert skip is None
        assert "score" in scores
        assert scores["score"] == 0.85


class TestRagTemplateMissingRequiredKey:
    @pytest.mark.parametrize(
        "factory,missing_field",
        [
            (faithfulness_template, "retrieved_context"),
            (context_relevance_template, "retrieved_context"),
            (context_precision_template, "retrieved_context"),
            (hallucination_template, "retrieved_context"),
            (answer_correctness_template, "reference_answer"),
        ],
        ids=[
            "faithfulness",
            "context_relevance",
            "context_precision",
            "hallucination",
            "answer_correctness",
        ],
    )
    def test_check_required_vars_fails_when_data_missing(self, factory, missing_field):
        props = factory(_MODEL, _PROVIDER)
        eval_input = EvalTaskInput(
            final_message="Some answer",
            task_input="Some question",
            reference_data=None,
        )
        skip, detail = check_required_vars(props.required_var, eval_input)
        assert skip == SkippedReason.extraction_failed
        assert detail is not None
        assert "undefined" in detail.lower()

    def test_answer_relevance_task_input_none_still_passes(self):
        """task_input=None is not Undefined, so check_required_vars passes.

        The required_var check only catches truly absent keys, not None values.
        """
        props = answer_relevance_template(_MODEL, _PROVIDER)
        eval_input = EvalTaskInput(
            final_message="Some answer",
            task_input=None,
        )
        skip, detail = check_required_vars(props.required_var, eval_input)
        assert skip is None
        assert detail is None

    def test_all_present_returns_no_skip(self):
        props = faithfulness_template(_MODEL, _PROVIDER)
        eval_input = EvalTaskInput(
            final_message="Some answer",
            task_input="Some question",
            reference_data={
                "retrieved_context": ["chunk1", "chunk2"],
            },
        )
        skip, detail = check_required_vars(props.required_var, eval_input)
        assert skip is None
        assert detail is None
