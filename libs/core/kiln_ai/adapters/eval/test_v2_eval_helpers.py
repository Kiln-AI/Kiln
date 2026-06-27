"""Tests for v2_eval_helpers -- extract_value, check_required_vars, check_reference_key, stringify_for_match."""

from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    check_reference_key,
    check_required_vars,
    extract_value,
    stringify_for_match,
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


# ---------------------------------------------------------------------------
# fromjson extraction error → clean skip
# ---------------------------------------------------------------------------


class TestFromjsonExtractionSkip:
    def test_extract_value_fromjson_invalid_json_skips(self):
        inp = _make_input(final_message="not valid json {")
        value, skip, detail = extract_value("(final_message | fromjson).field", inp)
        assert value is None
        assert skip == SkippedReason.extraction_failed
        assert detail is not None
        assert "not valid JSON" in detail
        assert "(final_message | fromjson).field" in detail

    def test_check_required_vars_fromjson_invalid_json_skips(self):
        inp = _make_input(final_message="plain text")
        skip, detail = check_required_vars(["(final_message | fromjson).key"], inp)
        assert skip == SkippedReason.extraction_failed
        assert detail is not None
        assert "not valid JSON" in detail

    def test_extract_value_fromjson_valid_json_passes(self):
        inp = _make_input(final_message='{"status": "ok"}')
        value, skip, _detail = extract_value("(final_message | fromjson).status", inp)
        assert value == "ok"
        assert skip is None


# ---------------------------------------------------------------------------
# stringify_for_match
# ---------------------------------------------------------------------------


class TestStringifyForMatch:
    def test_string_passthrough(self):
        assert stringify_for_match("hello") == "hello"

    def test_dict_to_json(self):
        result = stringify_for_match({"a": 1, "b": 2})
        assert result == '{"a": 1, "b": 2}'
        assert '"' in result

    def test_list_to_json(self):
        result = stringify_for_match([1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_bool_true(self):
        assert stringify_for_match(True) == "true"

    def test_bool_false(self):
        assert stringify_for_match(False) == "false"

    def test_number(self):
        assert stringify_for_match(42) == "42"

    def test_float(self):
        assert stringify_for_match(3.14) == "3.14"

    def test_none(self):
        assert stringify_for_match(None) == "null"

    def test_non_serializable_falls_back_to_str(self):
        assert stringify_for_match(object.__class__) == str(object.__class__)
