"""Tests for PatternMatchEval adapter."""

import pytest

from kiln_ai.adapters.eval.conftest import make_eval_task_input, make_v2_eval_config
from kiln_ai.adapters.eval.v2_eval_pattern_match import PatternMatchEval
from kiln_ai.datamodel.eval import (
    EvalTaskInput,
    PatternMatchProperties,
    SkippedReason,
)

_make_config = make_v2_eval_config


def _inp(**overrides: object) -> EvalTaskInput:
    final_message = overrides.pop("final_message", "Hello world 42")
    return make_eval_task_input(final_message=str(final_message), **overrides)


class TestPatternMatchMustMatch:
    @pytest.mark.asyncio
    async def test_pass_simple_pattern(self):
        cfg = _make_config(PatternMatchProperties(pattern=r"\d+"))
        result = await PatternMatchEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_fail_simple_pattern(self):
        cfg = _make_config(PatternMatchProperties(pattern=r"^\d+$"))
        result = await PatternMatchEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_anchored_pattern_pass(self):
        cfg = _make_config(PatternMatchProperties(pattern=r"^Hello"))
        result = await PatternMatchEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_word_boundary(self):
        cfg = _make_config(PatternMatchProperties(pattern=r"\bworld\b"))
        result = await PatternMatchEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 1.0}


class TestPatternMatchMustNotMatch:
    @pytest.mark.asyncio
    async def test_pass_must_not_match(self):
        cfg = _make_config(
            PatternMatchProperties(pattern=r"^ZZZZZ$", mode="must_not_match")
        )
        result = await PatternMatchEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_fail_must_not_match(self):
        cfg = _make_config(
            PatternMatchProperties(pattern=r"\d+", mode="must_not_match")
        )
        result = await PatternMatchEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}


class TestPatternMatchExpression:
    @pytest.mark.asyncio
    async def test_custom_expression(self):
        cfg = _make_config(
            PatternMatchProperties(
                pattern=r"^traced$", value_expression="trace[0].content"
            )
        )
        inp = _inp(trace=[{"content": "traced"}])
        result = await PatternMatchEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_undefined_expression_skips(self):
        cfg = _make_config(
            PatternMatchProperties(pattern=".*", value_expression="nonexistent_field")
        )
        result = await PatternMatchEval(cfg).evaluate(_inp())
        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.extraction_failed


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
