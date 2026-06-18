"""Tests for v2_eval_helpers -- extract_value, check_required_vars, check_reference_key."""

from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    check_reference_key,
    check_required_vars,
    extract_value,
)
from kiln_ai.datamodel.eval import EvalTaskInput, SkippedReason


def _make_input(**kwargs) -> EvalTaskInput:
    defaults = {"final_message": "hello"}
    defaults.update(kwargs)
    return EvalTaskInput(**defaults)


# ---------------------------------------------------------------------------
# extract_value
# ---------------------------------------------------------------------------


class TestExtractValue:
    def test_default_returns_final_message(self):
        inp = _make_input(final_message="the answer")
        value, skip, detail = extract_value(None, inp)
        assert value == "the answer"
        assert skip is None
        assert detail is None

    def test_valid_expression(self):
        inp = _make_input(final_message="hi", task_input="my input")
        value, skip, _detail = extract_value("task_input", inp)
        assert value == "my input"
        assert skip is None

    def test_undefined_expression_skips(self):
        inp = _make_input()
        value, skip, detail = extract_value("nonexistent_field", inp)
        assert value is None
        assert skip == SkippedReason.extraction_failed
        assert detail is not None and "undefined" in detail

    def test_none_result_skips(self):
        inp = _make_input(trace=None)
        value, skip, detail = extract_value("trace", inp)
        assert value is None
        assert skip == SkippedReason.extraction_failed
        assert detail is not None and "None" in detail

    def test_non_none_result_passes(self):
        inp = _make_input(trace=[{"role": "user", "content": "hi"}])
        value, skip, _detail = extract_value("trace", inp)
        assert value == [{"role": "user", "content": "hi"}]
        assert skip is None


# ---------------------------------------------------------------------------
# check_required_vars
# ---------------------------------------------------------------------------


class TestCheckRequiredVars:
    def test_all_present(self):
        inp = _make_input(final_message="hi", task_input="some input")
        skip, detail = check_required_vars(["final_message", "task_input"], inp)
        assert skip is None
        assert detail is None

    def test_undefined_var_skips(self):
        inp = _make_input()
        skip, detail = check_required_vars(["nonexistent"], inp)
        assert skip == SkippedReason.extraction_failed
        assert detail is not None and "undefined" in detail

    def test_none_var_skips(self):
        inp = _make_input(trace=None)
        skip, detail = check_required_vars(["trace"], inp)
        assert skip == SkippedReason.extraction_failed
        assert detail is not None and "None" in detail

    def test_empty_list_passes(self):
        inp = _make_input()
        skip, _detail = check_required_vars([], inp)
        assert skip is None

    def test_first_none_stops_early(self):
        inp = _make_input(trace=None, task_input="present")
        skip, detail = check_required_vars(["trace", "task_input"], inp)
        assert skip == SkippedReason.extraction_failed
        assert "trace" in (detail or "")


# ---------------------------------------------------------------------------
# check_reference_key
# ---------------------------------------------------------------------------


class TestCheckReferenceKey:
    def test_key_present_with_value(self):
        inp = _make_input(reference_data={"expected": "gold"})
        value, skip, _detail = check_reference_key("expected", inp)
        assert value == "gold"
        assert skip is None

    def test_no_reference_data(self):
        inp = _make_input(reference_data=None)
        value, skip, _detail = check_reference_key("expected", inp)
        assert value is None
        assert skip == SkippedReason.missing_reference_key

    def test_key_missing(self):
        inp = _make_input(reference_data={"other": "value"})
        value, skip, _detail = check_reference_key("expected", inp)
        assert value is None
        assert skip == SkippedReason.missing_reference_key

    def test_key_value_is_none_skips(self):
        inp = _make_input(reference_data={"expected": None})
        value, skip, detail = check_reference_key("expected", inp)
        assert value is None
        assert skip == SkippedReason.missing_reference_key
        assert detail is not None and "None" in detail
