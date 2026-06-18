"""Tests for ContainsEval adapter."""

import pytest

from kiln_ai.adapters.eval.conftest import make_eval_task_input, make_v2_eval_config
from kiln_ai.adapters.eval.v2_eval_contains import ContainsEval
from kiln_ai.datamodel.eval import (
    ContainsProperties,
    EvalTaskInput,
    SkippedReason,
)

_make_config = make_v2_eval_config


def _inp(**overrides: object) -> EvalTaskInput:
    final_message = overrides.pop("final_message", "Hello World 42")
    return make_eval_task_input(final_message=str(final_message), **overrides)


class TestContainsMustContain:
    @pytest.mark.asyncio
    async def test_pass_substring_present(self):
        cfg = _make_config(ContainsProperties(substring="World"))
        scores, skip, _ = await ContainsEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_fail_substring_absent(self):
        cfg = _make_config(ContainsProperties(substring="missing"))
        scores, skip, _ = await ContainsEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 0.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_case_sensitive_fail(self):
        cfg = _make_config(ContainsProperties(substring="world", case_sensitive=True))
        scores, _skip, _ = await ContainsEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 0.0}

    @pytest.mark.asyncio
    async def test_case_insensitive_pass(self):
        cfg = _make_config(ContainsProperties(substring="world", case_sensitive=False))
        scores, _skip, _ = await ContainsEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 1.0}


class TestContainsMustNotContain:
    @pytest.mark.asyncio
    async def test_pass_substring_absent(self):
        cfg = _make_config(
            ContainsProperties(substring="missing", mode="must_not_contain")
        )
        scores, _skip, _ = await ContainsEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_fail_substring_present(self):
        cfg = _make_config(
            ContainsProperties(substring="Hello", mode="must_not_contain")
        )
        scores, _skip, _ = await ContainsEval(cfg).evaluate(_inp())
        assert scores == {"score_a": 0.0}


class TestContainsReferenceKey:
    @pytest.mark.asyncio
    async def test_pass_with_reference_key(self):
        cfg = _make_config(ContainsProperties(reference_key="expected_sub"))
        inp = _inp(reference_data={"expected_sub": "Hello"})
        scores, skip, _ = await ContainsEval(cfg).evaluate(inp)
        assert scores == {"score_a": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_fail_with_reference_key(self):
        cfg = _make_config(ContainsProperties(reference_key="expected_sub"))
        inp = _inp(reference_data={"expected_sub": "nope"})
        scores, _skip, _ = await ContainsEval(cfg).evaluate(inp)
        assert scores == {"score_a": 0.0}

    @pytest.mark.asyncio
    async def test_missing_reference_data(self):
        cfg = _make_config(ContainsProperties(reference_key="expected_sub"))
        scores, skip, _detail = await ContainsEval(cfg).evaluate(_inp())
        assert scores == {}
        assert skip == SkippedReason.missing_reference_key

    @pytest.mark.asyncio
    async def test_missing_reference_key_in_data(self):
        cfg = _make_config(ContainsProperties(reference_key="expected_sub"))
        inp = _inp(reference_data={"other": "val"})
        scores, skip, _ = await ContainsEval(cfg).evaluate(inp)
        assert scores == {}
        assert skip == SkippedReason.missing_reference_key


class TestContainsExpression:
    @pytest.mark.asyncio
    async def test_custom_expression(self):
        cfg = _make_config(
            ContainsProperties(substring="traced", value_expression="trace[0].content")
        )
        inp = _inp(trace=[{"content": "This has traced data"}])
        scores, _skip, _ = await ContainsEval(cfg).evaluate(inp)
        assert scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_undefined_expression_skips(self):
        cfg = _make_config(
            ContainsProperties(substring="x", value_expression="nonexistent_field")
        )
        scores, skip, _detail = await ContainsEval(cfg).evaluate(_inp())
        assert scores == {}
        assert skip == SkippedReason.extraction_failed


class TestContainsNoScores:
    def test_no_parent_eval_raises(self):
        cfg = _make_config(ContainsProperties(substring="Hello"))
        cfg.parent_eval.return_value = None
        with pytest.raises(ValueError, match="parent eval"):
            ContainsEval(cfg)
