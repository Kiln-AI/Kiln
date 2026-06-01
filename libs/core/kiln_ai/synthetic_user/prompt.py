"""Persona-playing system prompt rendered per request for the synthetic user.

The prompt is built once per case (when the driver is constructed) and
reused across all turns. No early-termination guidance — the drive loop
runs for a fixed number of turns; the SU is told to stay engaged across
the whole conversation rather than try to wrap up early.
"""

from kiln_ai.synthetic_user.models import SyntheticUserInfo

_OPENING = (
    "You are playing the role of a user interacting with an AI assistant. "
    "Stay in character — respond as the user would, not as the assistant."
)

_CONVENTIONS = """## Conversation style
- Reply naturally and conversationally, as a real user would.
- React to what the assistant actually said in their last message.
- Keep replies short (one or two sentences) unless the situation calls for more detail.
- Do not narrate your own behavior ("As a user, I will now…"). Speak as the user.
- Stay engaged across the whole conversation. The drive loop runs for a fixed number of turns; do not try to wrap up, conclude, or end the conversation early. Keep asking follow-ups, varying approach as needed."""


def render_system_prompt(info: SyntheticUserInfo) -> str:
    """Render the persona-playing system prompt for one eval case."""
    sections = [
        _OPENING,
        f"## Your persona\n{info.persona}",
        f"## Your goal in this conversation\n{info.goal}",
    ]
    if info.behavior_guidance:
        sections.append(f"## How you behave\n{info.behavior_guidance}")
    sections.append(_CONVENTIONS)
    return "\n\n".join(sections)
