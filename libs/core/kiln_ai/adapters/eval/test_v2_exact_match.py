"""Tests for ExactMatchEval adapter."""

from unittest.mock import Mock

import pytest

from kiln_ai.adapters.eval.conftest import make_eval_task_input, make_v2_eval_config
from kiln_ai.adapters.eval.v2_eval_exact_match import ExactMatchEval
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    EvalOutputScore,
    ExactMatchProperties,
    SkippedReason,
)

_make_config = make_v2_eval_config
_inp = make_eval_task_input


class TestExactMatchBasic:
    @pytest.mark.asyncio
    async def test_pass_case_sensitive(self):
        cfg = _make_config(ExactMatchProperties(expected_value="Hello world"))
        scores, _skip, _detail = await ExactMatchEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 1.0}
        assert _skip is None

    @pytest.mark.asyncio
    async def test_fail_case_sensitive(self):
        cfg = _make_config(ExactMatchProperties(expected_value="hello world"))
        scores, _skip, _detail = await ExactMatchEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 0.0}
        assert _skip is None

    @pytest.mark.asyncio
    async def test_pass_case_insensitive(self):
        cfg = _make_config(
            ExactMatchProperties(expected_value="hello world", case_sensitive=False)
        )
        scores, _skip, _detail = await ExactMatchEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_fail_case_insensitive(self):
        cfg = _make_config(
            ExactMatchProperties(expected_value="nope", case_sensitive=False)
        )
        scores, _skip, _detail = await ExactMatchEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 0.0}


class TestExactMatchReferenceKey:
    @pytest.mark.asyncio
    async def test_pass_with_reference_key(self):
        cfg = _make_config(ExactMatchProperties(reference_key="answer"))
        inp = _inp(reference_data={"answer": "Hello world"})
        scores, skip, _ = await ExactMatchEval(cfg).evaluate(inp)
        assert scores == {"score_a": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_fail_with_reference_key(self):
        cfg = _make_config(ExactMatchProperties(reference_key="answer"))
        inp = _inp(reference_data={"answer": "wrong"})
        scores, _skip, _ = await ExactMatchEval(cfg).evaluate(inp)
        assert scores == {"score_a": 0.0}

    @pytest.mark.asyncio
    async def test_missing_reference_data(self):
        cfg = _make_config(ExactMatchProperties(reference_key="answer"))
        inp = _inp(reference_data=None)
        scores, skip, _detail = await ExactMatchEval(cfg).evaluate(inp)
        assert scores == {}
        assert skip == SkippedReason.missing_reference_key

    @pytest.mark.asyncio
    async def test_missing_reference_key_in_data(self):
        cfg = _make_config(ExactMatchProperties(reference_key="answer"))
        inp = _inp(reference_data={"other": "val"})
        scores, skip, _ = await ExactMatchEval(cfg).evaluate(inp)
        assert scores == {}
        assert skip == SkippedReason.missing_reference_key


class TestExactMatchExpression:
    @pytest.mark.asyncio
    async def test_value_expression(self):
        cfg = _make_config(ExactMatchProperties(expected_value="traced"))
        inp = _inp(trace=[{"content": "traced"}])
        scores, _skip, _ = await ExactMatchEval(cfg).evaluate(inp)
        # value_expression is None → uses final_message, not trace
        assert scores == {"score_a": 0.0}

    @pytest.mark.asyncio
    async def test_custom_expression(self):
        cfg = _make_config(
            ExactMatchProperties(
                expected_value="traced", value_expression="trace[0].content"
            )
        )
        inp = _inp(trace=[{"content": "traced"}])
        scores, _skip, _ = await ExactMatchEval(cfg).evaluate(inp)
        assert scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_undefined_expression_skips(self):
        cfg = _make_config(
            ExactMatchProperties(
                expected_value="x", value_expression="nonexistent_field"
            )
        )
        scores, skip, detail = await ExactMatchEval(cfg).evaluate(_inp())
        assert scores == {}
        assert skip == SkippedReason.extraction_failed
        assert detail is not None


class TestExactMatchNoScores:
    def test_no_parent_eval_raises(self):
        cfg = _make_config(ExactMatchProperties(expected_value="Hello world"))
        cfg.parent_eval.return_value = None
        with pytest.raises(ValueError, match="parent eval"):
            ExactMatchEval(cfg)

    @pytest.mark.asyncio
    async def test_no_output_scores_returns_empty(self):
        parent = Mock()
        parent.output_scores = []
        cfg = _make_config(ExactMatchProperties(expected_value="Hello world"))
        cfg.parent_eval.return_value = parent
        scores, skip, _ = await ExactMatchEval(cfg).evaluate(_inp())
        assert scores == {}
        assert skip is None


class TestExactMatchMultipleScores:
    @pytest.mark.asyncio
    async def test_all_scores_get_same_value(self):
        parent = Mock()
        parent.output_scores = [
            EvalOutputScore(
                name="score_a", instruction="a", type=TaskOutputRatingType.pass_fail
            ),
            EvalOutputScore(
                name="score_b", instruction="b", type=TaskOutputRatingType.pass_fail
            ),
        ]
        cfg = _make_config(ExactMatchProperties(expected_value="Hello world"))
        cfg.parent_eval.return_value = parent
        scores, _, _ = await ExactMatchEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 1.0, "score_b": 1.0}
