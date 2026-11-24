import pytest

from kiln_ai.datamodel.eval import EvalInput, SingleTurnEvalInputData, UserMessage
from kiln_ai.eval_grounding.judge_guidance import (
    is_grounded_input,
    render_judge_guidance,
)
from kiln_ai.eval_grounding.models import Evidence, Fact, GroundedReference


def _reference(**overrides) -> GroundedReference:
    fields = {
        "starting_point": "Two open tickets belong to the support agent.",
        "facts": [
            Fact(
                text="Ticket 7 is open.",
                evidence=Evidence(
                    tool="get_ticket",
                    args={"id": 7},
                    result_excerpt='{"id": 7, "status": "open"}',
                ),
            ),
            Fact(
                text="Ticket 9 is assigned to Dana.",
                evidence=Evidence(
                    tool="list_tickets",
                    args={"assignee": "Dana", "status": "open"},
                    result_excerpt="9: Pump check\n12: Valve swap",
                ),
            ),
        ],
        "expected_outcome": "Ticket 7 is on hold. Ticket 9 is unchanged.",
    }
    fields.update(overrides)
    return GroundedReference(**fields)


def test_renders_every_section_in_order():
    assert render_judge_guidance(_reference()) == (
        "## Starting point\n"
        "Two open tickets belong to the support agent.\n\n"
        "## Facts\n"
        "- Ticket 7 is open.\n"
        '  Checked with `get_ticket` ({"id": 7}): {"id": 7, "status": "open"}\n'
        "- Ticket 9 is assigned to Dana.\n"
        '  Checked with `list_tickets` ({"assignee": "Dana", "status": "open"}): '
        "9: Pump check\n"
        "  12: Valve swap\n\n"
        "## Expected outcome\n"
        "Ticket 7 is on hold. Ticket 9 is unchanged."
    )


def test_empty_parts_keep_their_heading_with_none():
    rendered = render_judge_guidance(
        _reference(starting_point=" ", facts=[], expected_outcome="")
    )
    assert rendered == (
        "## Starting point\nNone.\n\n## Facts\nNone.\n\n## Expected outcome\nNone."
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
