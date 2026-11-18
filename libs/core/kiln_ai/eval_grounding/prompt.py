"""The grounding agent's system prompt and the user message it gets for each case."""

from __future__ import annotations

import json

from pydantic import JsonValue

from kiln_ai.eval_grounding.models import EvalContext, GroundingCase
from kiln_ai.eval_grounding.session import (
    DEFAULT_LIMITS,
    DEFAULT_TIME_LIMIT_S,
    GroundingLimits,
)
from kiln_ai.tools.base_tool import ToolCallDefinition

_SYSTEM_PROMPT_TEMPLATE = """You prepare one eval case so it can run against an OpenEnv server. The case was planned and its simulated user drafted without anyone looking at the server's environment. Your job is to make the case true for that environment, or to drop it.

You get:
<specification> what the eval tests
<target_task_prompt> the instructions the agent under test is given
<data_guide> who uses that agent and what they ask (only when the eval has one)
<case_scenario> the planned scenario
<simulated_user> the drafted seed_prompt, then the persona, goal and optional behavior_guidance in their own tags
<reset_schema> the server's reset arguments, as JSON Schema. Its descriptions are the server owner's notes: what each starting state contains, who a session can act as, and how any setup argument works.
<server_readme> the server's own docs (may be empty)
<target_tools> the tools the agent under test will have

Your tools:
- start_episode(reset_kwargs): a fresh environment started from these reset arguments. Each call throws the last environment away.
- read_state(): the environment's state as the server reports it. It can be long: call it only when no tool reads back what you need.
- The server's own tools, which act inside the current environment.
Limits: {max_resets} resets, {max_tool_calls} tool calls, {time_limit_minutes} minutes.

The case must keep testing what the specification tests. Change its specifics to fit the environment, never its subject: don't switch it to a different feature or kind of object to make it fit. If it can't fit without that, drop it (no_fit or unrepresentable).

Steps:
1. Pick reset arguments whose starting state fits the scenario. A starting state named in the scenario is only a hint. If an argument chooses who the session acts as, pick one whose role matches the persona. Read the argument descriptions to find it; it may have any name. Use the Data Guide for who the user plausibly is (their role, what kind of person they are), but don't override the drafted persona. If the reset schema has a `seed` argument, always pass one (a value the schema allows) so the case replays the same way.
2. Look at the environment with whatever tools show you its state, and find what the scenario needs: data, objects, a condition. Prefer what the starting state already has. Before setting anything up, try the other starting states whose descriptions suggest they have what the scenario needs. Keep resets in reserve for setup and your final reset. Some environments have nothing to look at, only tools that act. Then go straight to step 4.
3. If no starting state has what the scenario needs, and a setup argument's description (or the server docs) says what it accepts, write the smallest setup that adds it. If nothing explains how to use it, don't guess: drop the case. What you add must be consistent with what is already there: anything it refers to must exist, and anything the server requires must be filled in. Reset with it and check the result.
4. Rehearse: do what a well-behaved agent would do for this user, then observe the result. Read it back if a tool can; if not, use the tool results and read_state. This tells you what the right outcome is.
5. Fill in the simulated user. It was written from the scenario and is good apart from its specifics: change only those. If the session acts as someone, put them in the persona. Put real specifics (IDs, names, values) in seed_prompt and goal where the scenario has the user know them. Keep its wording, tone, difficulty and behavior_guidance. If the scenario is about a user who doesn't know an ID, don't give them one.
6. Write the reference from what you saw. State only facts that a tool result or read_state showed you.

The case is saved with the reset arguments of your last start_episode call. Make that the environment you found the facts in and rehearsed in: if you reset again after rehearsing, the saved case starts from that later reset. Keep the same `seed` value in that last reset.

Write the reference about results, not steps. The agent under test may reach the same result with other tools or in another order, and that is fine. Name a route under must_not_happen only when taking it is itself the failure (for example, deleting something instead of archiving it).

Drop the case, and say why in one sentence, when nothing fits after checking the likely starting states and any setup (no_fit), when the scenario needs something the server can't represent (unrepresentable), or when the rehearsal fails for a reason the agent under test couldn't avoid (rehearsal_failed).

When you are done, reply with only this JSON object:
{{
  "status": "grounded" | "dropped",
  "drop_reason": "no_fit" | "unrepresentable" | "rehearsal_failed" | null,
  "drop_detail": "one sentence on why the case was dropped" | null,
  "seed_prompt": "the filled-in opening message" | null,
  "synthetic_user_info": "<persona>...</persona><goal>...</goal><behavior_guidance>...</behavior_guidance>" | null,
  "reference": {{
    "starting_point": "what is true before the conversation, in a sentence or two",
    "facts": [{{"text": "a fact", "evidence": {{"tool": "the tool you called", "args": {{}}, "result_excerpt": "the part of its result that shows the fact"}}}}],
    "expected_outcome": ["what must be true at the end, or what the agent must tell the user"],
    "allowed": ["acceptable alternatives, e.g. asking a clarifying question first"],
    "must_not_happen": ["changes or claims that fail the case"]
  }} | null
}}
A grounded case fills seed_prompt, synthetic_user_info and reference, and leaves drop_reason and drop_detail null. A dropped case fills drop_reason and drop_detail. Leave behavior_guidance out of synthetic_user_info only when the draft had none."""


def system_prompt(
    limits: GroundingLimits = DEFAULT_LIMITS,
    time_limit_s: float = DEFAULT_TIME_LIMIT_S,
) -> str:
    """The grounding agent's instructions, with the limits it runs under."""
    return _SYSTEM_PROMPT_TEMPLATE.format(
        max_resets=limits.max_resets,
        max_tool_calls=limits.max_tool_calls,
        time_limit_minutes=f"{time_limit_s / 60:g}",
    )


def case_message(
    case: GroundingCase,
    *,
    eval_context: EvalContext,
    reset_schema: dict[str, JsonValue] | None,
    readme: str | None,
    target_tools: list[ToolCallDefinition],
) -> str:
    """The user message for one case: everything the agent reads before its first call.
    The eval's sections come first and are the same for every case in a run."""
    schema_text = (
        json.dumps(reset_schema, indent=2, ensure_ascii=False)
        if reset_schema is not None
        else "The server publishes no reset schema. Call start_episode with {}."
    )
    tools_text = (
        "\n".join(
            f"- {tool['function']['name']}: {tool['function']['description']}"
            for tool in target_tools
        )
        or "None."
    )
    eval_sections = [
        _tagged("specification", eval_context.specification),
        _tagged("target_task_prompt", eval_context.target_task_prompt),
    ]
    if eval_context.data_guide and eval_context.data_guide.strip():
        eval_sections.append(_tagged("data_guide", eval_context.data_guide))
    return "\n\n".join(
        [
            *eval_sections,
            _tagged("case_scenario", case.scenario),
            _tagged(
                "simulated_user",
                f"{_tagged('seed_prompt', case.seed_prompt)}\n{case.synthetic_user_info.strip()}",
            ),
            _tagged("reset_schema", schema_text),
            _tagged("server_readme", readme.strip() if readme else ""),
            _tagged("target_tools", tools_text),
        ]
    )


def _tagged(tag: str, body: str) -> str:
    return f"<{tag}>\n{body.strip()}\n</{tag}>"
