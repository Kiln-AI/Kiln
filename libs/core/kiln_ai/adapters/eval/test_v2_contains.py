"""Tests for ContainsEval adapter."""

from unittest.mock import Mock

import pytest

from kiln_ai.adapters.eval.v2_eval_contains import ContainsEval
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    ContainsProperties,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
    SkippedReason,
)


def _make_config(props: ContainsProperties) -> EvalConfig:
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
        "final_message": "Hello World 42",
        "trace": None,
        "reference_data": None,
        "task_input": None,
    }
    defaults.update(overrides)
    return EvalTaskInput(**defaults)


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
    @pytest.mark.asyncio
    async def test_no_parent_eval_returns_empty(self):
        cfg = _make_config(ContainsProperties(substring="Hello"))
        cfg.parent_eval.return_value = None
        scores, skip, _ = await ContainsEval(cfg).evaluate(_inp())
        assert scores == {}
        assert skip is None
