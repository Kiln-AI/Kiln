"""Tests for PatternMatchEval adapter."""

from unittest.mock import Mock

import pytest

from kiln_ai.adapters.eval.v2_eval_pattern_match import PatternMatchEval
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
    PatternMatchProperties,
    SkippedReason,
)


def _make_config(props: PatternMatchProperties) -> EvalConfig:
    parent = Mock()
    parent.output_scores = [
        EvalOutputScore(
            name="score_a", instruction="a", type=TaskOutputRatingType.pass_fail
        ),
    ]
    cfg = Mock(spec=EvalConfig)
    cfg.config_type = EvalConfigType.v2
    cfg.properties = props
    cfg.parent_eval.return_value = parent
    return cfg


def _inp(**overrides) -> EvalTaskInput:
    defaults: dict = {
        "final_message": "Hello world 42",
        "trace": None,
        "reference_data": None,
        "task_input": None,
    }
    defaults.update(overrides)
    return EvalTaskInput(**defaults)


class TestPatternMatchMustMatch:
    @pytest.mark.asyncio
    async def test_pass_simple_pattern(self):
        cfg = _make_config(PatternMatchProperties(pattern=r"\d+"))
        scores, skip, _ = await PatternMatchEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_fail_simple_pattern(self):
        cfg = _make_config(PatternMatchProperties(pattern=r"^\d+$"))
        scores, skip, _ = await PatternMatchEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 0.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_anchored_pattern_pass(self):
        cfg = _make_config(PatternMatchProperties(pattern=r"^Hello"))
        scores, _skip, _ = await PatternMatchEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_word_boundary(self):
        cfg = _make_config(PatternMatchProperties(pattern=r"\bworld\b"))
        scores, _skip, _ = await PatternMatchEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 1.0}


class TestPatternMatchMustNotMatch:
    @pytest.mark.asyncio
    async def test_pass_must_not_match(self):
        cfg = _make_config(
            PatternMatchProperties(pattern=r"^ZZZZZ$", mode="must_not_match")
        )
        scores, _skip, _ = await PatternMatchEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_fail_must_not_match(self):
        cfg = _make_config(
            PatternMatchProperties(pattern=r"\d+", mode="must_not_match")
        )
        scores, _skip, _ = await PatternMatchEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 0.0}


class TestPatternMatchExpression:
    @pytest.mark.asyncio
    async def test_custom_expression(self):
        cfg = _make_config(
            PatternMatchProperties(
                pattern=r"^traced$", value_expression="trace[0].content"
            )
        )
        inp = _inp(trace=[{"content": "traced"}])
        scores, _skip, _ = await PatternMatchEval(cfg).evaluate(inp)
        assert scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_undefined_expression_skips(self):
        cfg = _make_config(
            PatternMatchProperties(pattern=".*", value_expression="nonexistent_field")
        )
        scores, skip, _detail = await PatternMatchEval(cfg).evaluate(_inp())
        assert scores == {}
        assert skip == SkippedReason.extraction_failed


class TestPatternMatchNoScores:
    def test_no_parent_eval_raises(self):
        cfg = _make_config(PatternMatchProperties(pattern=".*"))
        cfg.parent_eval.return_value = None
        with pytest.raises(ValueError, match="parent eval"):
            PatternMatchEval(cfg)


class TestPatternMatchValidation:
    def test_invalid_regex_rejected_at_model_creation(self):
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            PatternMatchProperties(pattern="[invalid")

    def test_valid_regex_accepted(self):
        props = PatternMatchProperties(pattern=r"^[a-z]+$")
        assert props.pattern == r"^[a-z]+$"
