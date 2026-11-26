---
name: context_on_tool_surface
description: Template for a context tool that carries a rule in its description and the tool's own status in its response, for a rule in the prompt that the model breaks at a tool call.
---

# Wrapper template: context_on_tool_surface

**Failure in the trace:** A rule for a call or for the reply after it sits in the prompt, and the model breaks it before, with or after a tool call.

**What it does for the model:** A context tool whose DESCRIPTION carries the rule (when to call it, how the reply uses its result) and whose RESPONSE `notes` field states the tool's own status: derived facts, a fixable error, or how the tool works - never an order.

Copy the module below into the `code` field of a code tool, after the
three edits and under the rules of
`references/knowledge/code_tool_authoring.md`.

```python
"""context_on_tool_surface — put the context and its rule on the tool surface.

The measured finding behind this template: five instruction-text candidates
told the model to address the user by name, and every one won on train
and lost at val, because the failing message was emitted BEFORE or WITH
the first tool call — the name did not exist in context yet. The one
candidate that survived put the contract on the tool surface.

This template keeps that shape. The tool DESCRIPTION carries the rule:
when to call the tool, and how the reply uses its result. The RESPONSE
carries only the tool's own status, in a `notes` field: derived facts, a
fixable error or the next valid action, or a fact about how the tool
works. `notes` is never an order to the agent. A rule about the reply in
general goes in the description, and it moves out of the prompt.

tool_description (the half that matters — write it for that decision
point): "Call this FIRST, before any other tool or any reply. It returns
who you are talking to and the current time. Your first sentence must
address the user by the display name it returns. When it returns no
display name, greet the user without a name, and never use the user id as
a name. Do not narrate which tools you will call."

parameters_schema: {"type": "object", "properties": {}}

No nested calls; allowlist empty. `_context()` is a PLACEHOLDER: replace
it with the subject's real context source (a user lookup, a clock, a
config record) before you POST the tool. The values it returns are
markers, not data.
"""

from datetime import datetime, timezone


def _context():
    """REPLACE ME: the subject's real user/context lookup."""
    return {
        "id": "<REPLACE: user id>",
        "display_name": "<REPLACE: display name>",
        "role": "<REPLACE: role>",
    }


def _notes(user):
    """The tool's own status: facts about the result, never an order."""
    name = user.get("display_name")
    who = (
        f"signed-in user: {name}"
        if name
        else f"no display name on record for user {user.get('id')}"
    )
    return f"{who}; `now` is UTC"


def run():
    user = _context()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {"user": user, "now": now, "notes": _notes(user)}
```
