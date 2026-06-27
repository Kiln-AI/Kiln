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
        result = await ContainsEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_fail_substring_absent(self):
        cfg = _make_config(ContainsProperties(substring="missing"))
        result = await ContainsEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_case_sensitive_fail(self):
        cfg = _make_config(ContainsProperties(substring="world", case_sensitive=True))
        result = await ContainsEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}

    @pytest.mark.asyncio
    async def test_case_insensitive_pass(self):
        cfg = _make_config(ContainsProperties(substring="world", case_sensitive=False))
        result = await ContainsEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 1.0}


class TestContainsMustNotContain:
    @pytest.mark.asyncio
    async def test_pass_substring_absent(self):
        cfg = _make_config(
            ContainsProperties(substring="missing", mode="must_not_contain")
        )
        result = await ContainsEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_fail_substring_present(self):
        cfg = _make_config(
            ContainsProperties(substring="Hello", mode="must_not_contain")
        )
        result = await ContainsEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}


class TestContainsReferenceKey:
    @pytest.mark.asyncio
    async def test_pass_with_reference_key(self):
        cfg = _make_config(ContainsProperties(reference_key="expected_sub"))
        inp = _inp(reference_data={"expected_sub": "Hello"})
        result = await ContainsEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_fail_with_reference_key(self):
        cfg = _make_config(ContainsProperties(reference_key="expected_sub"))
        inp = _inp(reference_data={"expected_sub": "nope"})
        result = await ContainsEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 0.0}

    @pytest.mark.asyncio
    async def test_missing_reference_data(self):
        cfg = _make_config(ContainsProperties(reference_key="expected_sub"))
        result = await ContainsEval(cfg).evaluate(_inp())
        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.missing_reference_key

    @pytest.mark.asyncio
    async def test_missing_reference_key_in_data(self):
        cfg = _make_config(ContainsProperties(reference_key="expected_sub"))
        inp = _inp(reference_data={"other": "val"})
        result = await ContainsEval(cfg).evaluate(inp)
        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.missing_reference_key


class TestContainsExpression:
    @pytest.mark.asyncio
    async def test_custom_expression(self):
        cfg = _make_config(
            ContainsProperties(substring="traced", value_expression="trace[0].content")
        )
        inp = _inp(trace=[{"content": "This has traced data"}])
        result = await ContainsEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_undefined_expression_fails_not_skips(self):
        cfg = _make_config(
            ContainsProperties(substring="x", value_expression="nonexistent_field")
        )
        result = await ContainsEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_fromjson_invalid_json_fails_not_skips(self):
        cfg = _make_config(
            ContainsProperties(
                substring="x",
                value_expression="(final_message | fromjson).field",
            )
        )
        inp = _inp(final_message="not json")
        result = await ContainsEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 0.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_must_not_contain_undefined_output_still_fails(self):
        """A must_not_contain check with undefined output should FAIL, not pass.

        Even though the undefined value trivially "doesn't contain" the substring,
        the correct semantics is: the model didn't produce the expected field, so
        the eval result is a failure.
        """
        cfg = _make_config(
            ContainsProperties(
                substring="anything",
                mode="must_not_contain",
                value_expression="nonexistent_field",
            )
        )
        result = await ContainsEval(cfg).evaluate(_inp())
        assert result.scores == {"score_a": 0.0}
        assert result.skipped_reason is None


class TestContainsJsonCoercion:
    @pytest.mark.asyncio
    async def test_dict_value_contains_json_key(self):
        cfg = _make_config(
            ContainsProperties(
                substring='"status"',
                value_expression="(final_message | fromjson).result",
            )
        )
        inp = _inp(final_message='{"result": {"status": "ok", "code": 200}}')
        result = await ContainsEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_list_value_contains_element(self):
        cfg = _make_config(
            ContainsProperties(
                substring="2",
                value_expression="(final_message | fromjson).numbers",
            )
        )
        inp = _inp(final_message='{"numbers": [1, 2, 3]}')
        result = await ContainsEval(cfg).evaluate(inp)
        assert result.scores == {"score_a": 1.0}


class TestContainsNoScores:
    def test_no_parent_eval_raises(self):
        cfg = _make_config(ContainsProperties(substring="Hello"))
        cfg.parent_eval.return_value = None
        with pytest.raises(ValueError, match="parent eval"):
            ContainsEval(cfg)
