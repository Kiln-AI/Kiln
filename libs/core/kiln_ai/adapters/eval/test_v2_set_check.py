"""Tests for SetCheckEval adapter."""

import pytest

from kiln_ai.adapters.eval.conftest import make_eval_task_input, make_v2_eval_config
from kiln_ai.adapters.eval.v2_eval_set_check import SetCheckEval
from kiln_ai.datamodel.eval import (
    EvalTaskInput,
    SetCheckProperties,
    SkippedReason,
)

_make_config = make_v2_eval_config


def _inp(**overrides: object) -> EvalTaskInput:
    final_message = overrides.pop("final_message", '["a", "b"]')
    return make_eval_task_input(final_message=str(final_message), **overrides)


class TestSetCheckSubset:
    @pytest.mark.asyncio
    async def test_pass_subset(self):
        cfg = _make_config(
            SetCheckProperties(expected_set=["a", "b", "c"], mode="subset")
        )
        result = await SetCheckEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_fail_subset(self):
        cfg = _make_config(SetCheckProperties(expected_set=["a"], mode="subset"))
        result = await SetCheckEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}

    @pytest.mark.asyncio
    async def test_equal_sets_pass_subset(self):
        cfg = _make_config(SetCheckProperties(expected_set=["a", "b"], mode="subset"))
        result = await SetCheckEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 1.0}


class TestSetCheckSuperset:
    @pytest.mark.asyncio
    async def test_pass_superset(self):
        cfg = _make_config(SetCheckProperties(expected_set=["a"], mode="superset"))
        result = await SetCheckEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_fail_superset(self):
        cfg = _make_config(
            SetCheckProperties(expected_set=["a", "b", "c"], mode="superset")
        )
        result = await SetCheckEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}


class TestSetCheckEqual:
    @pytest.mark.asyncio
    async def test_pass_equal(self):
        cfg = _make_config(SetCheckProperties(expected_set=["a", "b"], mode="equal"))
        result = await SetCheckEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_fail_equal_extra(self):
        cfg = _make_config(
            SetCheckProperties(expected_set=["a", "b", "c"], mode="equal")
        )
        result = await SetCheckEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}

    @pytest.mark.asyncio
    async def test_fail_equal_missing(self):
        cfg = _make_config(SetCheckProperties(expected_set=["a"], mode="equal"))
        result = await SetCheckEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}


class TestSetCheckCoercion:
    @pytest.mark.asyncio
    async def test_string_json_list(self):
        cfg = _make_config(SetCheckProperties(expected_set=["x", "y"], mode="equal"))
        inp = _inp(final_message='["x", "y"]')
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_string_non_json_becomes_single_element(self):
        cfg = _make_config(SetCheckProperties(expected_set=["hello"], mode="equal"))
        inp = _inp(final_message="hello")
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_dict_keys(self):
        cfg = _make_config(
            SetCheckProperties(
                expected_set=["a", "b"],
                mode="equal",
                value_expression="reference_data",
            )
        )
        inp = _inp(reference_data={"a": 1, "b": 2})
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_list_value_via_expression(self):
        cfg = _make_config(
            SetCheckProperties(
                expected_set=["x", "y"],
                mode="equal",
                value_expression="trace[0].elements",
            )
        )
        inp = _inp(trace=[{"elements": ["x", "y"]}])
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_numeric_list_stringified(self):
        cfg = _make_config(SetCheckProperties(expected_set=["1", "2"], mode="equal"))
        inp = _inp(final_message="[1, 2]")
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}


class TestSetCheckReferenceKey:
    @pytest.mark.asyncio
    async def test_pass_with_reference_key(self):
        cfg = _make_config(SetCheckProperties(reference_key="expected", mode="equal"))
        inp = _inp(
            final_message='["a", "b"]',
            reference_data={"expected": ["a", "b"]},
        )
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_missing_reference_data(self):
        cfg = _make_config(SetCheckProperties(reference_key="expected", mode="equal"))
        result = await SetCheckEval(cfg).evaluate(_inp())
        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.missing_reference_key

    @pytest.mark.asyncio
    async def test_missing_reference_key_in_data(self):
        cfg = _make_config(SetCheckProperties(reference_key="expected", mode="equal"))
        inp = _inp(reference_data={"other": "val"})
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.missing_reference_key


class TestSetCheckExpression:
    @pytest.mark.asyncio
    async def test_undefined_expression_fails_not_skips(self):
        cfg = _make_config(
            SetCheckProperties(
                expected_set=["a"],
                value_expression="nonexistent_field",
                mode="equal",
            )
        )
        result = await SetCheckEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_fromjson_invalid_json_fails_not_skips(self):
        cfg = _make_config(
            SetCheckProperties(
                expected_set=["a"],
                value_expression="(final_message | fromjson).field",
                mode="equal",
            )
        )
        inp = _inp(final_message="not json")
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 0.0}
        assert result.skipped_reason is None


class TestSetCheckNoScores:
    def test_no_parent_eval_raises(self):
        cfg = _make_config(SetCheckProperties(expected_set=["a", "b"], mode="equal"))
        cfg.parent_eval.return_value = None
        with pytest.raises(ValueError, match="parent eval"):
            SetCheckEval(cfg)


class TestSetCheckEmptySet:
    @pytest.mark.asyncio
    async def test_empty_subset_passes(self):
        cfg = _make_config(SetCheckProperties(expected_set=[], mode="subset"))
        inp = _inp(final_message="[]")
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_empty_superset_of_nonempty_fails(self):
        cfg = _make_config(SetCheckProperties(expected_set=["a"], mode="superset"))
        inp = _inp(final_message="[]")
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 0.0}

    @pytest.mark.asyncio
    async def test_empty_equal_to_empty(self):
        cfg = _make_config(SetCheckProperties(expected_set=[], mode="equal"))
        inp = _inp(final_message="[]")
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_empty_not_equal_to_nonempty(self):
        cfg = _make_config(SetCheckProperties(expected_set=["a"], mode="equal"))
        inp = _inp(final_message="[]")
        result = await SetCheckEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 0.0}


class TestCoerceToSetStatic:
    @pytest.mark.parametrize(
        "input_val, expected",
        [
            (["a", "b"], {"a", "b"}),
            ({"x": 1, "y": 2}, {"x", "y"}),
            ('["a", "b"]', {"a", "b"}),
            ("plain", {"plain"}),
            ([1, 2, 3], {"1", "2", "3"}),
            (42, {"42"}),
            (set(["a", "b"]), {"a", "b"}),
        ],
    )
    def test_coerce(self, input_val, expected):
        assert SetCheckEval._coerce_to_set(input_val) == expected

    def test_bool_coercion_uses_json_style(self):
        result = SetCheckEval._coerce_to_set([True, False, 42])
        assert result == {"true", "false", "42"}

    def test_json_array_with_bool_coercion(self):
        result = SetCheckEval._coerce_to_set("[true, false, 1]")
        assert result == {"true", "false", "1"}
