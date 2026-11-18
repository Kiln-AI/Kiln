import copy
import json
from typing import get_args

import jsonschema
import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.json_schema import close_object_schemas
from kiln_ai.datamodel.openenv import OpenEnvReset
from kiln_ai.eval_grounding.models import (
    DropReason,
    GroundedReference,
    GroundingOutcome,
    GroundingResult,
    LoggedCall,
    ModelDropReason,
    result_json_schema,
)
from kiln_ai.synthetic_user.parser import SyntheticUserInfoParseError
from kiln_ai.utils.usage import Usage

USER_INFO = "<persona>Dana, a technician</persona><goal>Put #804 on hold</goal>"

REFERENCE = {
    "starting_point": "Work orders #803 and #804 are open.",
    "facts": [
        {
            "text": "#804 is open and assigned to Dana.",
            "evidence": {
                "tool": "list_work_orders",
                "args": {"status": "open", "limit": 5},
                "result_excerpt": '{"id": 804, "assignee": "Dana"}',
            },
        }
    ],
    "expected_outcome": ["#804 is on hold"],
    "allowed": ["Asking which work order first"],
    "must_not_happen": ["#803 changes"],
}


def _grounded_result(**overrides):
    return {
        "status": "grounded",
        "seed_prompt": "Put #804 on hold please",
        "synthetic_user_info": USER_INFO,
        "reference": REFERENCE,
        **overrides,
    }


def test_grounded_result_parses():
    result = GroundingResult.model_validate(_grounded_result())
    assert result.reference is not None
    assert result.reference.facts[0].evidence.args == {"status": "open", "limit": 5}


@pytest.mark.parametrize("missing", ["seed_prompt", "synthetic_user_info", "reference"])
def test_grounded_result_needs_its_fields(missing):
    with pytest.raises(ValidationError, match=f"needs {missing}"):
        GroundingResult.model_validate(_grounded_result(**{missing: None}))


def test_grounded_result_has_no_drop_reason():
    with pytest.raises(ValidationError, match="no drop reason"):
        GroundingResult.model_validate(_grounded_result(drop_reason="no_fit"))


def test_grounded_result_needs_a_parseable_user():
    with pytest.raises(ValidationError) as exc_info:
        GroundingResult.model_validate(
            _grounded_result(synthetic_user_info="<persona>only a persona</persona>")
        )
    assert isinstance(
        exc_info.value.errors()[0]["ctx"]["error"], SyntheticUserInfoParseError
    )


def test_dropped_result_needs_reason_and_detail():
    dropped = GroundingResult.model_validate(
        {"status": "dropped", "drop_reason": "no_fit", "drop_detail": "No fixture."}
    )
    assert dropped.drop_reason == "no_fit"
    with pytest.raises(ValidationError, match="needs drop_reason and drop_detail"):
        GroundingResult.model_validate({"status": "dropped", "drop_reason": "no_fit"})
    with pytest.raises(ValidationError, match="needs drop_reason and drop_detail"):
        GroundingResult.model_validate({"status": "dropped", "drop_detail": "Why."})


@pytest.mark.parametrize("reason", ["limit", "invalid_output", "other"])
def test_model_cannot_choose_kiln_drop_reasons(reason):
    with pytest.raises(ValidationError):
        GroundingResult.model_validate(
            {"status": "dropped", "drop_reason": reason, "drop_detail": "Why."}
        )


def test_grounded_outcome_needs_a_reset():
    fields = {
        "status": "grounded",
        "seed_prompt": "hi",
        "synthetic_user_info": USER_INFO,
        "reference": REFERENCE,
    }
    with pytest.raises(ValidationError, match="needs openenv_reset"):
        GroundingOutcome.model_validate(fields)
    outcome = GroundingOutcome.model_validate(
        {
            **fields,
            "openenv_reset": OpenEnvReset(
                openenv_server_id="srv", reset_kwargs={"fixture": "agency"}
            ),
        }
    )
    assert outcome.call_log == []
    assert outcome.usage is None


def test_dropped_outcome_takes_kiln_reasons():
    outcome = GroundingOutcome(
        status="dropped", drop_reason=DropReason.limit, drop_detail="Ran out of calls."
    )
    assert outcome.drop_reason == DropReason.limit
    with pytest.raises(ValidationError, match="needs drop_reason and drop_detail"):
        GroundingOutcome(status="dropped", drop_reason=DropReason.limit)


def test_reference_dumps_to_the_eval_input_shape():
    reference = GroundedReference.model_validate(REFERENCE)
    assert reference.model_dump() == REFERENCE


def test_dropped_result_does_not_parse_the_user():
    result = GroundingResult(
        status="dropped",
        drop_reason="no_fit",
        drop_detail="x",
        synthetic_user_info="not tagged",
    )
    assert result.synthetic_user_info == "not tagged"


def test_model_drop_reasons_are_drop_reasons():
    assert {DropReason(r) for r in get_args(ModelDropReason)} == {
        DropReason.no_fit,
        DropReason.unrepresentable,
        DropReason.rehearsal_failed,
    }


def _logged_call():
    return LoggedCall(
        tool="start_episode",
        args={"reset_kwargs": {}},
        output="{}",
        is_error=False,
        episode_id="ep_1",
    )


def test_from_result_takes_the_given_reset_not_the_model_one():
    reset = OpenEnvReset(openenv_server_id="srv", reset_kwargs={"fixture": "a"})
    usage = Usage(input_tokens=10, output_tokens=2)
    outcome = GroundingOutcome.from_result(
        GroundingResult.model_validate(_grounded_result()),
        openenv_reset=reset,
        call_log=[_logged_call()],
        usage=usage,
    )
    assert outcome.status == "grounded"
    assert outcome.openenv_reset == reset
    assert outcome.seed_prompt == "Put #804 on hold please"
    assert outcome.synthetic_user_info == USER_INFO
    assert outcome.reference is not None
    assert outcome.reference.expected_outcome == ["#804 is on hold"]
    assert outcome.call_log == [_logged_call()]
    assert outcome.usage == usage


def test_from_result_without_a_reset_is_an_invalid_output_drop():
    outcome = GroundingOutcome.from_result(
        GroundingResult.model_validate(_grounded_result()),
        openenv_reset=None,
        call_log=[],
        usage=None,
    )
    assert outcome.status == "dropped"
    assert outcome.drop_reason == DropReason.invalid_output
    assert outcome.drop_detail
    assert outcome.reference is None


def test_from_result_keeps_the_model_drop():
    outcome = GroundingOutcome.from_result(
        GroundingResult(
            status="dropped", drop_reason="no_fit", drop_detail="Nothing fits."
        ),
        openenv_reset=OpenEnvReset(openenv_server_id="srv"),
        call_log=[_logged_call()],
        usage=None,
    )
    assert outcome.status == "dropped"
    assert outcome.drop_reason == DropReason.no_fit
    assert outcome.drop_detail == "Nothing fits."
    assert outcome.openenv_reset is None
    assert outcome.call_log == [_logged_call()]


def test_dropped_builds_a_valid_drop():
    outcome = GroundingOutcome.dropped(
        DropReason.limit, "Out of time.", call_log=[], usage=None
    )
    assert outcome.status == "dropped"
    assert outcome.drop_reason == DropReason.limit
    assert outcome.drop_detail == "Out of time."


def _with_encoded_args(result: dict) -> dict:
    facts = [
        {
            **fact,
            "evidence": {
                **fact["evidence"],
                "args": json.dumps(fact["evidence"]["args"], ensure_ascii=False),
            },
        }
        for fact in result["reference"]["facts"]
    ]
    return {**result, "reference": {**result["reference"], "facts": facts}}


def _as_the_model_answers(result: dict) -> dict:
    """`result` with every field present, as the schema requires."""
    return {"drop_reason": None, "drop_detail": None, **result}


DROPPED_RESULT = {
    "status": "dropped",
    "drop_reason": "no_fit",
    "drop_detail": "No open work order.",
    "seed_prompt": None,
    "synthetic_user_info": None,
    "reference": None,
}


class TestResultJsonSchema:
    @pytest.mark.parametrize("encoded", [True, False])
    def test_names_every_field(self, encoded):
        schema = result_json_schema(args_as_json_string=encoded)
        assert list(schema["properties"]) == list(GroundingResult.model_fields)
        reference = schema["properties"]["reference"]["anyOf"][0]
        assert list(reference["properties"]) == list(GroundedReference.model_fields)
        assert schema["properties"]["drop_reason"]["enum"] == [
            *get_args(ModelDropReason),
            None,
        ]

    def test_results_validate_under_strict_closing(self):
        schema = close_object_schemas(
            result_json_schema(args_as_json_string=True), strict=True
        )
        jsonschema.validate(
            _as_the_model_answers(_with_encoded_args(_grounded_result())), schema
        )
        jsonschema.validate(DROPPED_RESULT, schema)

    def test_strict_closing_would_empty_object_args(self):
        schema = close_object_schemas(
            result_json_schema(args_as_json_string=False), strict=True
        )
        with pytest.raises(jsonschema.ValidationError, match="Additional properties"):
            jsonschema.validate(_as_the_model_answers(_grounded_result()), schema)

    def test_object_args_validate_when_not_closed(self):
        jsonschema.validate(
            _as_the_model_answers(_grounded_result()),
            result_json_schema(args_as_json_string=False),
        )


class TestFromModelOutput:
    def test_decodes_args_strings(self):
        result = GroundingResult.from_model_output(
            _with_encoded_args(_grounded_result()), args_as_json_string=True
        )
        assert result.reference is not None
        assert result.reference.facts[0].evidence.args == {"status": "open", "limit": 5}

    @pytest.mark.parametrize(
        "args, message", [("[1]", "must be a JSON object"), ("{oops", "not valid JSON")]
    )
    def test_rejects_args_that_are_not_an_object(self, args, message):
        output = copy.deepcopy(_grounded_result())
        output["reference"]["facts"][0]["evidence"]["args"] = args
        with pytest.raises(ValueError, match=message):
            GroundingResult.from_model_output(output, args_as_json_string=True)

    def test_object_args_pass_through_when_not_encoded(self):
        result = GroundingResult.from_model_output(
            _grounded_result(), args_as_json_string=False
        )
        assert result.reference is not None
        assert result.reference.facts[0].evidence.args["limit"] == 5

    def test_a_drop_has_no_facts_to_decode(self):
        result = GroundingResult.from_model_output(
            DROPPED_RESULT, args_as_json_string=True
        )
        assert result.drop_reason == "no_fit"
