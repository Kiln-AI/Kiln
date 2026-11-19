"""The markdown a judge reads for a grounded case, saved under the reference key
`judge_guidance`."""

from __future__ import annotations

import json

from kiln_ai.datamodel.eval import EvalInput
from kiln_ai.eval_grounding.models import Fact, GroundedReference

JUDGE_GUIDANCE_REFERENCE_KEY = "judge_guidance"
"""The reference key a grounded case's guidance is saved under, on eval inputs and golden
task runs alike."""


def is_grounded_input(eval_input: EvalInput) -> bool:
    """True when the eval input was grounded in its OpenEnv server: its reference carries
    judge guidance."""
    return (
        eval_input.reference is not None
        and JUDGE_GUIDANCE_REFERENCE_KEY in eval_input.reference
    )


def render_judge_guidance(reference: GroundedReference) -> str:
    """One heading per part of the reference, in a fixed order. Each fact is followed by the
    call that showed it. An empty list keeps its heading, with "None." under it."""
    sections = [
        ("Starting point", reference.starting_point.strip() or "None."),
        ("Facts", _bullets([_fact(fact) for fact in reference.facts])),
        ("Expected outcome", _bullets(reference.expected_outcome)),
        ("Allowed", _bullets(reference.allowed)),
        ("Must not happen", _bullets(reference.must_not_happen)),
    ]
    return "\n\n".join(f"## {heading}\n{body}" for heading, body in sections)


def _fact(fact: Fact) -> str:
    evidence = fact.evidence
    args = json.dumps(evidence.args, ensure_ascii=False)
    return (
        f"{fact.text.strip()}\n"
        f"Checked with `{evidence.tool}` ({args}): {evidence.result_excerpt.strip()}"
    )


def _bullets(items: list[str]) -> str:
    if not items:
        return "None."
    # Later lines of an item are indented under its bullet, so a multi-line item stays one
    # list item.
    return "\n".join("- " + "\n  ".join(item.strip().splitlines()) for item in items)
