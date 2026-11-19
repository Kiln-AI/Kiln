import pytest

from kiln_ai.datamodel.eval import EvalInput, SingleTurnEvalInputData, UserMessage
from kiln_ai.eval_grounding.judge_guidance import (
    is_grounded_input,
    render_judge_guidance,
)
from kiln_ai.eval_grounding.models import Evidence, Fact, GroundedReference


def _reference(**overrides) -> GroundedReference:
    fields = {
        "starting_point": "Two open work orders belong to the technician.",
        "facts": [
            Fact(
                text="Work order 7 is open.",
                evidence=Evidence(
                    tool="get_work_order",
                    args={"id": 7},
                    result_excerpt='{"id": 7, "status": "open"}',
                ),
            ),
            Fact(
                text="Work order 9 is assigned to Dana.",
                evidence=Evidence(
                    tool="list_work_orders",
                    args={"assignee": "Dana", "status": "open"},
                    result_excerpt="9: Pump check\n12: Valve swap",
                ),
            ),
        ],
        "expected_outcome": ["Work order 7 is on hold.", "The agent says so."],
        "allowed": ["Asking which work order first."],
        "must_not_happen": ["Work order 7 is closed."],
    }
    fields.update(overrides)
    return GroundedReference(**fields)


def test_renders_every_section_in_order():
    assert render_judge_guidance(_reference()) == (
        "## Starting point\n"
        "Two open work orders belong to the technician.\n\n"
        "## Facts\n"
        "- Work order 7 is open.\n"
        '  Checked with `get_work_order` ({"id": 7}): {"id": 7, "status": "open"}\n'
        "- Work order 9 is assigned to Dana.\n"
        '  Checked with `list_work_orders` ({"assignee": "Dana", "status": "open"}): '
        "9: Pump check\n"
        "  12: Valve swap\n\n"
        "## Expected outcome\n"
        "- Work order 7 is on hold.\n"
        "- The agent says so.\n\n"
        "## Allowed\n"
        "- Asking which work order first.\n\n"
        "## Must not happen\n"
        "- Work order 7 is closed."
    )


def test_empty_lists_keep_their_heading_with_none():
    rendered = render_judge_guidance(
        _reference(facts=[], expected_outcome=[], allowed=[], must_not_happen=[])
    )
    for heading in ("Facts", "Expected outcome", "Allowed", "Must not happen"):
        assert f"## {heading}\nNone." in rendered
    assert rendered.startswith(
        "## Starting point\nTwo open work orders belong to the technician."
    )


@pytest.mark.parametrize(
    "reference, grounded",
    [
        (None, False),
        ({"answer": "4"}, False),
        ({"judge_guidance": "## Starting point\nX."}, True),
    ],
)
def test_is_grounded_input(reference, grounded):
    eval_input = EvalInput(
        data=SingleTurnEvalInputData(user_message=UserMessage(text="hi")),
        reference=reference,
    )
    assert is_grounded_input(eval_input) is grounded
