"""The grounding agent's system prompt and the user message it gets for each case."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import JsonValue

from kiln_ai.eval_grounding.models import EvalContext, GroundingCase
from kiln_ai.eval_grounding.session import (
    DEFAULT_LIMITS,
    DEFAULT_TIME_LIMIT_S,
    SUBMIT_RESULT_TOOL,
    GroundingLimits,
)
from kiln_ai.tools.base_tool import ToolCallDefinition

AnswerStyle = Literal["reply_json", "structured_output", "submit_result"]
"""How the agent hands back its result: as its final reply's text (`claude -p`), in the
JSON response format Kiln sets, or through the `submit_result` tool."""

KilnAnswerStyle = Literal["structured_output", "submit_result"]
"""The answer styles a run on a Kiln model can use."""

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

The things the scenario and the simulated user name (a product, a customer, a record, an app, a person) were made up without seeing the environment. When one isn't there, that is not a reason to drop the case. Use one of the same kind that the environment has, or add one with setup, and use its real name everywhere in the simulated user. Only the kind of thing matters, not its name. Drop for no_fit only when nothing of that kind exists and setup can't add it.

Keep the situation the scenario describes: when something happened, whose it is, what state it is in. If the starting state doesn't have that situation, add it with setup rather than changing the situation, so the case still tests the same thing.

Before you drop a case for no_fit or rehearsal_failed, try at least one other way: another starting state, an existing item of the same kind, or another tool that reaches the same result.

Steps:
1. Pick reset arguments whose starting state fits the scenario. A starting state named in the scenario is only a hint. If an argument chooses who the session acts as, pick one whose role matches the persona. Read the argument descriptions to find it; it may have any name. Use the Data Guide for who the user plausibly is (their role, what kind of person they are), but don't override the drafted persona. If the reset schema has a `seed` argument, always pass one (a value the schema allows) so the case replays the same way.
2. Look at the environment with whatever tools show you its state, and find what the scenario needs: data, objects, a condition. Prefer what the starting state already has. Before setting anything up, try the other starting states whose descriptions suggest they have what the scenario needs. Keep resets in reserve for setup and your final reset. Some environments have nothing to look at, only tools that act. Then go straight to step 4.
3. If no starting state has what the scenario needs, and a setup argument's description (or the server docs) says what it accepts, write the smallest setup that adds it. If nothing explains how to use it, don't guess: drop the case. What you add must be consistent with what is already there: anything it refers to must exist, and anything the server requires must be filled in. Make it look like the environment's own data, so nothing in it reads as test data to the agent under test: copy an existing item of the same kind and change only what the case needs, and follow the environment's own style for IDs, numbers, names and dates. Write the data the scenario calls for as the scenario describes it. Don't soften, mask or sanitize it to fit the specification: if the scenario needs offensive text in a record, write that text, not a masked version of it, or the case tests something else. Reset with it and check the result.
4. Rehearse: do what a well-behaved agent would do for this user, then observe the result. Read it back if a tool can; if not, use the tool results and read_state. This tells you what the right outcome is.
5. Fill in the simulated user. It was written from the scenario and is good apart from its specifics: change only those. If the session acts as someone, put them in the persona. Put real specifics (IDs, names, values) in seed_prompt and goal where the scenario has the user know them. Keep its wording, tone, difficulty and behavior_guidance. If the scenario is about a user who doesn't know an ID, don't give them one.
6. Write the reference from what you saw. State only facts that a tool result or read_state showed you.

The case is saved with the reset arguments of your last start_episode call. Make that the environment you found the facts in and rehearsed in: if you reset again after rehearsing, the saved case starts from that later reset. Keep the same `seed` value in that last reset.

The reference holds the facts of the environment and nothing else. Don't restate or interpret the specification: the judge has it, and decides what the agent should do with these facts. Write only what the environment shows.
- starting_point: what the environment holds before the conversation, including anything your setup added. If the environment has a clock or a time zone, give them: dates in the facts and the outcome are read against them.
- facts: what you found, each with the call that showed it. The call's result must show the whole fact; if it shows only part, make another call or narrow the fact. The call must make sense on its own: if it only reads the saved output of an earlier call, cite the earlier call instead.
- expected_outcome: one short paragraph: the correct answer the agent should be able to give, and any change the environment should show at the end. Check in your rehearsal what actually changed, and describe it the way the server records it, including the fields the server set on its own (a timestamp, who made the change) so the judge doesn't count them as extra. You may name a plausible wrong answer as a fact (for example, "the full list has 28 items; a search by title finds only 18"). Don't say how the agent should word its reply or what rule it should follow: no "the agent should ask", "the reply should name", "is wrong" or "is acceptable". Don't label a change as allowed, forbidden, extra or unrequested, and don't decide what the user's words permit: give the facts the judge needs to decide that (for example, "only one user has the technician role") and let the judge apply the specification. Where the right end state depends on what the user answers, give the end state for each answer.

Name every item the reference talks about the way a person would (its title or number) and by the identifier the environment's state uses for it, so the judge can find it in the final state. That includes look-alike items that must stay unchanged.

Write the reference about results, not steps. The agent under test may reach the same result with other tools or in another order, and that is fine.

Drop the case, and say why in one sentence, when nothing fits after checking the likely starting states and any setup (no_fit), when the scenario needs something the server can't represent (unrepresentable), or when the rehearsal fails for a reason the agent under test couldn't avoid (rehearsal_failed).

A case that expects the agent under test to refuse is unrepresentable when the server itself doesn't refuse the request or enforce the rule behind it. Drop it, and say in drop_detail that the server doesn't enforce it.

{final_answer}"""

_RESULT_SKELETON = """{{
  "status": "grounded" | "dropped",
  "drop_reason": "no_fit" | "unrepresentable" | "rehearsal_failed" | null,
  "drop_detail": "one sentence on why the case was dropped" | null,
  "seed_prompt": "the filled-in opening message" | null,
  "synthetic_user_info": "<persona>...</persona><goal>...</goal><behavior_guidance>...</behavior_guidance>" | null,
  "reference": {{
    "starting_point": "what the environment holds before the conversation, including any setup you added, in a sentence or two",
    "facts": [{{"text": "a fact", "evidence": {{"tool": "the tool you called", "args": {args}, "result_excerpt": "the part of its result that shows the fact"}}}}],
    "expected_outcome": "one short paragraph: the correct answer and any change the environment should show at the end"
  }} | null
}}
A grounded case fills seed_prompt, synthetic_user_info and reference, and leaves drop_reason and drop_detail null. A dropped case fills drop_reason and drop_detail. Leave behavior_guidance out of synthetic_user_info only when the draft had none."""

_FINAL_ANSWER: dict[AnswerStyle, str] = {
    "reply_json": "When you are done, reply with only this JSON object:\n{skeleton}",
    "structured_output": (
        "When you are done, reply with your result as this JSON object:\n{skeleton}\n"
        "In each fact's evidence, args is a string that holds the JSON object of "
        'arguments you called the tool with, e.g. "{{\\"id\\": 7}}".'
    ),
    "submit_result": (
        f"When you are done, call {SUBMIT_RESULT_TOOL} once with your result:\n"
        "{skeleton}\n"
        f"If {SUBMIT_RESULT_TOOL} reports a problem, fix it and call it again. Once it "
        "accepts your result, reply with only the word done."
    ),
}


def system_prompt(
    limits: GroundingLimits = DEFAULT_LIMITS,
    time_limit_s: float = DEFAULT_TIME_LIMIT_S,
    answer_style: AnswerStyle = "reply_json",
) -> str:
    """The grounding agent's instructions, with the limits it runs under and how it
    hands back its result."""
    skeleton = _RESULT_SKELETON.format(
        args='"{\\"id\\": 7}"' if answer_style == "structured_output" else "{}"
    )
    return _SYSTEM_PROMPT_TEMPLATE.format(
        max_resets=limits.max_resets,
        max_tool_calls=limits.max_tool_calls,
        time_limit_minutes=f"{time_limit_s / 60:g}",
        final_answer=_FINAL_ANSWER[answer_style].format(skeleton=skeleton),
    )


def follow_up_message(error: str, answer_style: AnswerStyle) -> str:
    """The one follow-up, in the same conversation, after a result that could not be
    used. The agent's environment tools are closed by then."""
    if answer_style == "submit_result":
        return (
            f"{error}\n\nCall {SUBMIT_RESULT_TOOL} with your result now. Your other "
            "tools are closed."
        )
    return (
        f"Your last reply could not be used: {error}\n\n"
        "Reply with only the JSON object your instructions describe, and nothing else."
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
