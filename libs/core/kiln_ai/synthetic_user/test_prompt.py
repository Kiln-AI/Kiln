"""Unit tests for the persona-playing system prompt template.

These are structural assertions — we don't check exact wording (that's
allowed to drift as we tune the persona prompt) but we DO check the
prompt has every required section and is free of the removed termination
guidance.
"""

from kiln_ai.synthetic_user.models import SyntheticUserInfo
from kiln_ai.synthetic_user.prompt import render_system_prompt


def _full_info() -> SyntheticUserInfo:
    return SyntheticUserInfo(
        persona="A 30-something professional, anxious about taxes.",
        goal="Find the 2016 RRSP contribution limit.",
        behavior_guidance="Press for specific numbers if the agent gives vague answers.",
    )


def test_includes_persona_text() -> None:
    info = _full_info()
    rendered = render_system_prompt(info)
    assert info.persona in rendered


def test_includes_goal_text() -> None:
    info = _full_info()
    rendered = render_system_prompt(info)
    assert info.goal in rendered


def test_includes_behavior_guidance_when_set() -> None:
    info = _full_info()
    rendered = render_system_prompt(info)
    assert info.behavior_guidance is not None
    assert info.behavior_guidance in rendered
    assert "How you behave" in rendered


def test_omits_behavior_guidance_section_when_none() -> None:
    info = SyntheticUserInfo(persona="P", goal="G")  # behavior_guidance = None
    rendered = render_system_prompt(info)
    assert "How you behave" not in rendered


def test_includes_conventions_block() -> None:
    rendered = render_system_prompt(_full_info())
    assert "Conversation style" in rendered


def test_does_not_include_termination_sentinels() -> None:
    # Decision: drive loop runs for fixed `turns`; SU must NOT try to end
    # the conversation. The template should carry no <DONE> / <CANCEL>
    # guidance.
    rendered = render_system_prompt(_full_info())
    assert "<DONE>" not in rendered
    assert "<CANCEL>" not in rendered
    assert "DONE" not in rendered  # also no bare-word leak
    assert "CANCEL" not in rendered


def test_section_order_opening_persona_goal_behavior_conventions() -> None:
    info = _full_info()
    rendered = render_system_prompt(info)
    assert info.behavior_guidance is not None

    # Use distinctive substrings from each section.
    opening_marker = "Stay in character"
    persona_section = "Your persona"
    goal_section = "Your goal in this conversation"
    behavior_section = "How you behave"
    conventions_marker = "Conversation style"

    indexes = [
        rendered.index(opening_marker),
        rendered.index(persona_section),
        rendered.index(goal_section),
        rendered.index(behavior_section),
        rendered.index(conventions_marker),
    ]
    assert indexes == sorted(indexes), f"Sections out of expected order: {indexes}"


def test_section_order_skips_behavior_when_none() -> None:
    info = SyntheticUserInfo(persona="P", goal="G")
    rendered = render_system_prompt(info)

    indexes = [
        rendered.index("Stay in character"),
        rendered.index("Your persona"),
        rendered.index("Your goal in this conversation"),
        rendered.index("Conversation style"),
    ]
    assert indexes == sorted(indexes)
