"""Characterization tests for GEval scoring methods.

These tests lock the current behavior of build_llm_as_judge_score and
build_g_eval_score BEFORE they are extracted into scoring_utils.py.
"""

import math
import pickle

import pytest

from kiln_ai.adapters.eval.g_eval import GEval
from kiln_ai.adapters.eval.test_g_eval_data import serialized_run_output
from kiln_ai.adapters.model_adapters.base_adapter import RunOutput
from kiln_ai.datamodel import (
    Project,
    Task,
    TaskOutputRatingType,
    TaskRequirement,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties


@pytest.fixture
def test_task(tmp_path):
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
        requirements=[
            TaskRequirement(
                name="Topic alignment",
                instruction="Rate alignment",
                type=TaskOutputRatingType.five_star,
            ),
            TaskRequirement(
                name="Appropriateness",
                instruction="Check appropriateness",
                type=TaskOutputRatingType.pass_fail,
            ),
        ],
    )
    task.save_to_file()
    return task


@pytest.fixture
def test_eval_config(test_task):
    eval = Eval(
        name="Test Eval",
        parent=test_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="appropriateness",
                type=TaskOutputRatingType.pass_fail,
            ),
            EvalOutputScore(
                name="topic_alignment",
                type=TaskOutputRatingType.five_star,
            ),
            EvalOutputScore(
                name="overall_rating",
                type=TaskOutputRatingType.five_star,
            ),
        ],
    )
    eval.save_to_file()

    config = EvalConfig(
        name="Test Eval Config",
        parent=eval,
        config_type=EvalConfigType.g_eval,
        model_name="gpt_4o_mini",
        model_provider="openai",
        properties={
            "eval_steps": [
                "Step one",
                "Step two",
            ]
        },
    )
    config.save_to_file()
    return config


@pytest.fixture
def test_run_config():
    return KilnAgentRunConfigProperties(
        model_name="llama_3_1_8b",
        model_provider_name=ModelProviderName.groq,
        prompt_id="simple_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_schema,
    )


@pytest.fixture
def g_eval_instance(test_eval_config, test_run_config):
    return GEval(test_eval_config, test_run_config)


class TestBuildLlmAsJudgeScore:
    def test_five_star_score(self, g_eval_instance):
        run_output = RunOutput(
            output={
                "topic_alignment": 4,
                "appropriateness": "pass",
                "overall_rating": 3,
            },
            intermediate_outputs={},
        )
        result = g_eval_instance.build_llm_as_judge_score(run_output)
        assert result["topic_alignment"] == 4.0
        assert result["appropriateness"] == 1.0
        assert result["overall_rating"] == 3.0

    def test_pass_fail_score(self, g_eval_instance):
        run_output = RunOutput(
            output={
                "topic_alignment": 5,
                "appropriateness": "fail",
                "overall_rating": 2,
            },
            intermediate_outputs={},
        )
        result = g_eval_instance.build_llm_as_judge_score(run_output)
        assert result["appropriateness"] == 0.0
        assert result["topic_alignment"] == 5.0
        assert result["overall_rating"] == 2.0

    def test_missing_metric_raises(self, g_eval_instance):
        run_output = RunOutput(
            output={
                "topic_alignment": "invalid_token",
                "appropriateness": "pass",
                "overall_rating": 3,
            },
            intermediate_outputs={},
        )
        with pytest.raises(ValueError, match="No score found for metric"):
            g_eval_instance.build_llm_as_judge_score(run_output)

    def test_non_dict_output_raises(self, g_eval_instance):
        run_output = RunOutput(
            output="not a dict",
            intermediate_outputs={},
        )
        with pytest.raises(
            ValueError, match="LLM as Judge output must be a dictionary"
        ):
            g_eval_instance.build_llm_as_judge_score(run_output)

    def test_serialized_run_output(self, g_eval_instance):
        """Lock behavior against the real serialized RunOutput from test_g_eval_data."""
        run_output = pickle.loads(serialized_run_output)
        assert isinstance(run_output, RunOutput)
        result = g_eval_instance.build_llm_as_judge_score(run_output)
        assert result["overall_rating"] == 4.0
        assert result["topic_alignment"] == 5.0
        assert result["appropriateness"] == 1.0


class TestBuildGEvalScore:
    def test_serialized_run_output(self, g_eval_instance):
        """Lock the exact weighted scores from the real serialized RunOutput."""
        run_output = pickle.loads(serialized_run_output)
        assert isinstance(run_output, RunOutput)
        result = g_eval_instance.build_g_eval_score(run_output)

        assert pytest.approx(result["overall_rating"]) == 3.99752802363598
        assert pytest.approx(result["topic_alignment"]) == 4.999983298485167
        assert pytest.approx(result["appropriateness"], 1e-12) == 0.9999999999572222

    def test_uniform_logprobs(self, g_eval_instance):
        """Uniform logprobs across rating tokens should produce a midpoint weighted average."""
        from litellm.types.utils import (
            ChatCompletionTokenLogprob,
            ChoiceLogprobs,
            TopLogprob,
        )

        prob = 1.0 / 5.0
        logprob_val = math.log(prob)

        top_logprobs = [
            TopLogprob(token=str(i), logprob=logprob_val, bytes=None)
            for i in range(1, 6)
        ]

        content_tokens = [
            ChatCompletionTokenLogprob(
                token="{", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="topic_alignment", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=":", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=" ", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="3", logprob=logprob_val, top_logprobs=top_logprobs, bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=",", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=" ", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="appropriateness", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=":", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=" ", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="pass",
                logprob=math.log(0.5),
                top_logprobs=[
                    TopLogprob(token="pass", logprob=math.log(0.5), bytes=None),
                    TopLogprob(token="fail", logprob=math.log(0.5), bytes=None),
                ],
                bytes=None,
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=",", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=" ", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="overall_rating", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=":", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=" ", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="5", logprob=logprob_val, top_logprobs=top_logprobs, bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="}", logprob=-0.01, top_logprobs=[], bytes=None
            ),
        ]

        run_output = RunOutput(
            output={
                "topic_alignment": 3,
                "appropriateness": "pass",
                "overall_rating": 5,
            },
            intermediate_outputs={},
            output_logprobs=ChoiceLogprobs(content=content_tokens),
        )

        result = g_eval_instance.build_g_eval_score(run_output)

        assert pytest.approx(result["topic_alignment"]) == 3.0
        assert pytest.approx(result["appropriateness"]) == 0.5
        assert pytest.approx(result["overall_rating"]) == 3.0

    def test_skewed_logprobs(self, g_eval_instance):
        """Logprobs heavily favoring '5' should produce a score close to 5.0."""
        from litellm.types.utils import (
            ChatCompletionTokenLogprob,
            ChoiceLogprobs,
            TopLogprob,
        )

        top_logprobs = [
            TopLogprob(token="5", logprob=math.log(0.95), bytes=None),
            TopLogprob(token="4", logprob=math.log(0.04), bytes=None),
            TopLogprob(token="3", logprob=math.log(0.01), bytes=None),
        ]

        content_tokens = [
            ChatCompletionTokenLogprob(
                token="{", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="topic_alignment", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=":", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=" ", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="5", logprob=math.log(0.95), top_logprobs=top_logprobs, bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=",", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=" ", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="appropriateness", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=":", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=" ", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="pass",
                logprob=math.log(0.99),
                top_logprobs=[
                    TopLogprob(token="pass", logprob=math.log(0.99), bytes=None),
                    TopLogprob(token="fail", logprob=math.log(0.01), bytes=None),
                ],
                bytes=None,
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=",", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=" ", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="overall_rating", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token='"', logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=":", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token=" ", logprob=-0.01, top_logprobs=[], bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="5", logprob=math.log(0.95), top_logprobs=top_logprobs, bytes=None
            ),
            ChatCompletionTokenLogprob(
                token="}", logprob=-0.01, top_logprobs=[], bytes=None
            ),
        ]

        run_output = RunOutput(
            output={
                "topic_alignment": 5,
                "appropriateness": "pass",
                "overall_rating": 5,
            },
            intermediate_outputs={},
            output_logprobs=ChoiceLogprobs(content=content_tokens),
        )

        result = g_eval_instance.build_g_eval_score(run_output)

        expected_five_star = 5.0 * 0.95 + 4.0 * 0.04 + 3.0 * 0.01
        assert result["topic_alignment"] > 4.5
        assert pytest.approx(result["topic_alignment"]) == expected_five_star
        assert result["overall_rating"] > 4.5
        expected_pass_fail = 1.0 * 0.99 + 0.0 * 0.01
        assert result["appropriateness"] > 0.9
        assert pytest.approx(result["appropriateness"]) == expected_pass_fail
