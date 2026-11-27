import hashlib
import json
import re

import pytest

from kiln_ai.eval_grounding.models import EvalContext, GroundingCase, GroundingResult
from kiln_ai.eval_grounding.prompt import (
    case_message,
    follow_up_message,
    system_prompt,
)
from kiln_ai.eval_grounding.session import (
    READ_STATE_TOOL,
    START_EPISODE_TOOL,
    GroundingLimits,
)

CASE = GroundingCase(
    scenario="A support agent asks to put one of their open tickets on hold.",
    seed_prompt="Can you put my pump job on hold?",
    synthetic_user_info="<persona>A support agent</persona>\n<goal>Hold the job</goal>\n",
)

EVAL_CONTEXT = EvalContext(
    specification="The agent puts tickets on hold only when asked.",
    target_task_prompt="Help support agents manage their tickets.",
    data_guide="Support leads triaging tickets, often between calls.\n",
)

TARGET_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tickets",
            "description": "List tickets.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_ticket",
            "description": "Change a ticket.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def test_case_message_carries_every_section():
    schema = {"properties": {"fixture": {"enum": ["agency"]}}}
    message = case_message(
        CASE,
        eval_context=EVAL_CONTEXT,
        reset_schema=schema,
        target_tools=TARGET_TOOLS,
    )
    assert message == (
        "<specification>\n"
        "The agent puts tickets on hold only when asked.\n"
        "</specification>\n\n"
        "<target_task_prompt>\n"
        "Help support agents manage their tickets.\n"
        "</target_task_prompt>\n\n"
        "<data_guide>\nSupport leads triaging tickets, often between calls.\n</data_guide>\n\n"
        "<case_scenario>\n"
        "A support agent asks to put one of their open tickets on hold.\n"
        "</case_scenario>\n\n"
        "<simulated_user>\n"
        "<seed_prompt>\nCan you put my pump job on hold?\n</seed_prompt>\n"
        "<persona>A support agent</persona>\n<goal>Hold the job</goal>\n"
        "</simulated_user>\n\n"
        f"<reset_schema>\n{json.dumps(schema, indent=2)}\n</reset_schema>\n\n"
        "<target_tools>\n"
        "- list_tickets: List tickets.\n"
        "- update_ticket: Change a ticket.\n"
        "</target_tools>"
    )


@pytest.mark.parametrize("data_guide", [None, "", "  "])
def test_case_message_without_data_guide_schema_or_tools(data_guide):
    message = case_message(
        CASE,
        eval_context=EVAL_CONTEXT.model_copy(update={"data_guide": data_guide}),
        reset_schema=None,
        target_tools=[],
    )
    assert message.startswith("<specification>\n")
    assert "<data_guide>" not in message
    assert (
        "<reset_schema>\nThe server publishes no reset schema. "
        "Call start_episode with {}.\n</reset_schema>"
    ) in message
    assert "server_readme" not in message
    assert "<target_tools>\nNone.\n</target_tools>" in message


def test_system_prompt_states_the_limits():
    prompt = system_prompt(GroundingLimits(max_tool_calls=12, max_resets=3), 300)
    assert "Limits: 3 resets, 12 tool calls, 5 minutes." in prompt


@pytest.mark.parametrize("rehearse", [False, True])
@pytest.mark.parametrize(
    "answer_style", ["reply_json", "structured_output", "submit_result"]
)
@pytest.mark.parametrize(
    ("mode", "case_fields", "other_fields"),
    [
        ("multi_turn", ("seed_prompt", "synthetic_user_info"), ("input",)),
        ("single_turn", ("input",), ("seed_prompt", "synthetic_user_info")),
    ],
)
def test_system_prompt_names_the_tools_and_every_result_field(
    answer_style, mode, case_fields, other_fields, rehearse
):
    prompt = system_prompt(answer_style=answer_style, mode=mode, rehearse=rehearse)
    if not rehearse:
        other_fields = (*other_fields, "rehearsal_reply")
    assert "Limits: 10 resets, 40 tool calls, 15 minutes." in prompt
    for tool in (START_EPISODE_TOOL, READ_STATE_TOOL):
        assert f"{tool}(" in prompt
    for field in GroundingResult.model_fields:
        if field not in other_fields:
            assert f'"{field}"' in prompt
    for field in other_fields:
        assert f'"{field}"' not in prompt
    assert all(f'"{field}"' in prompt for field in case_fields)
    for reason in ("no_fit", "unrepresentable", "rehearsal_failed"):
        assert reason in prompt


def test_system_prompt_lists_every_case_message_section():
    message = case_message(
        CASE,
        eval_context=EVAL_CONTEXT.model_copy(update={"max_turns": 1}),
        reset_schema=None,
        target_tools=[],
    )
    prompt = system_prompt(one_turn=True)
    for tag in re.findall(r"^<(\w+)>$", message, flags=re.MULTILINE):
        if tag != "seed_prompt":
            assert f"\n<{tag}> " in prompt


def test_case_message_gives_a_one_message_limit_after_the_simulated_user():
    message = case_message(
        CASE,
        eval_context=EVAL_CONTEXT.model_copy(update={"max_turns": 1}),
        reset_schema=None,
        target_tools=[],
    )
    assert (
        "</simulated_user>\n\n<turn_limit>\n1 message: seed_prompt is all the agent "
        "under test gets, and the conversation ends after its one reply.\n"
        "</turn_limit>\n\n"
    ) in message


@pytest.mark.parametrize("max_turns", [None, 2, 3, 20])
def test_case_message_of_more_than_one_message_is_as_before(max_turns):
    """Only a one-message limit changes what grounding is told."""
    message = case_message(
        CASE,
        eval_context=EVAL_CONTEXT.model_copy(update={"max_turns": max_turns}),
        reset_schema=None,
        target_tools=[],
    )
    assert message == case_message(
        CASE, eval_context=EVAL_CONTEXT, reset_schema=None, target_tools=[]
    )
    assert "<turn_limit>" not in message


def test_system_prompt_keeps_the_record_in_a_one_message_seed_prompt():
    """With one message the agent can't ask which record the user means, so the rule
    that strips the item the agent has to find must not strip the record's name."""
    assert "turn_limit" not in system_prompt()
    prompt = system_prompt(one_turn=True)
    assert "\n<turn_limit> how many messages the simulated user can send\n" in prompt
    assert (
        "The user can still name the item they mean when the agent asks. When "
        "<turn_limit> gives the user one message, the agent can't ask: keep in "
        "seed_prompt what the agent needs to identify the record the user means "
        "(its name, number or email), as the scenario has the user know it."
    ) in prompt


def test_single_turn_prompt_has_no_turn_limit():
    assert "turn_limit" not in system_prompt(mode="single_turn")
    with pytest.raises(ValueError, match="one_turn is for multi-turn"):
        system_prompt(mode="single_turn", one_turn=True)


def test_single_turn_context_refuses_a_turn_limit():
    with pytest.raises(ValueError, match="max_turns is for multi-turn"):
        EvalContext(
            specification="s",
            target_task_prompt="p",
            mode="single_turn",
            max_turns=1,
        )


SINGLE_TURN_CASE = GroundingCase(
    scenario="A support agent asks which of their tickets are on hold."
)

SINGLE_TURN_CONTEXT = EVAL_CONTEXT.model_copy(
    update={
        "mode": "single_turn",
        "input_schema": '{"type": "object", "properties": {"q": {"type": "string"}}}',
        "example_input": '{"q": "Which tickets are mine?"}',
    }
)


def test_single_turn_case_message_has_no_simulated_user():
    message = case_message(
        SINGLE_TURN_CASE,
        eval_context=SINGLE_TURN_CONTEXT,
        reset_schema=None,
        target_tools=TARGET_TOOLS,
    )
    assert "<simulated_user>" not in message
    assert (
        "<example_input>\n"
        '{"q": "Which tickets are mine?"}\n'
        "</example_input>\n\n"
        "<input_schema>\n"
        '{"type": "object", "properties": {"q": {"type": "string"}}}\n'
        "</input_schema>\n\n"
        "<case_scenario>\n"
        "A support agent asks which of their tickets are on hold.\n"
        "</case_scenario>"
    ) in message


def test_single_turn_case_message_leaves_out_what_the_task_lacks():
    message = case_message(
        SINGLE_TURN_CASE,
        eval_context=SINGLE_TURN_CONTEXT.model_copy(
            update={"input_schema": None, "example_input": None}
        ),
        reset_schema=None,
        target_tools=[],
    )
    assert "<example_input>" not in message
    assert "<input_schema>" not in message


def test_single_turn_prompt_lists_every_case_message_section():
    message = case_message(
        SINGLE_TURN_CASE,
        eval_context=SINGLE_TURN_CONTEXT,
        reset_schema=None,
        target_tools=[],
    )
    prompt = system_prompt(mode="single_turn")
    for tag in re.findall(r"^<(\w+)>$", message, flags=re.MULTILINE):
        assert f"\n<{tag}> " in prompt


@pytest.mark.parametrize(
    ("case", "eval_context"),
    [(CASE, SINGLE_TURN_CONTEXT), (SINGLE_TURN_CASE, EVAL_CONTEXT)],
)
def test_a_case_of_the_other_mode_is_refused(case, eval_context):
    with pytest.raises(ValueError, match="can't be grounded in"):
        case_message(
            case, eval_context=eval_context, reset_schema=None, target_tools=[]
        )


def test_single_turn_prompt_asks_for_an_input_not_a_simulated_user():
    prompt = system_prompt(mode="single_turn")
    assert "5. Write the input:" in prompt
    assert (
        "a JSON object that matches it, written into input as a JSON string" in prompt
    )
    for gone in ("simulated user", "persona", "seed_prompt", "what the user answers"):
        assert gone not in prompt


def test_neither_prompt_mentions_server_docs():
    for mode in ("multi_turn", "single_turn"):
        prompt = system_prompt(mode=mode)
        assert "server_readme" not in prompt
        assert "server docs" not in prompt


def test_each_answer_style_says_how_to_hand_back_the_result():
    assert "reply with only this JSON object:\n{" in system_prompt()
    assert '"args": {}' in system_prompt()

    structured = system_prompt(answer_style="structured_output")
    assert "reply with your result as this JSON object:\n{" in structured
    assert '"args": "{\\"id\\": 7}"' in structured
    assert "args is a string that holds the JSON object" in structured

    submit = system_prompt(answer_style="submit_result")
    assert "call submit_result once with your result:\n{" in submit
    assert '"args": {}' in submit
    assert submit.endswith("reply with only the word done.")


def test_system_prompt_has_the_refusal_and_recorded_change_rules():
    prompt = system_prompt()
    assert (
        "A case that expects the agent under test to refuse is unrepresentable when "
        "the server itself doesn't refuse the request or enforce the rule behind it."
    ) in prompt
    assert "say in drop_detail that the server doesn't enforce it" in prompt
    assert "describe it the way the server records it" in prompt


def test_system_prompt_keeps_the_reference_to_environment_facts():
    prompt = system_prompt()
    assert "Don't restate or interpret the specification: the judge has it" in prompt
    assert "Don't soften, mask or sanitize it to fit the specification" in prompt
    for removed in ("must_not_happen", '"allowed"'):
        assert removed not in prompt


def test_system_prompt_has_the_reading_simulated_user_evidence_and_setup_rules():
    prompt = system_prompt()
    assert "give the answer or end state for each reading" in prompt
    assert "without calling it the only correct one" in prompt
    assert "Then remove what a real user wouldn't say" in prompt
    assert "instructions that rescue the agent" in prompt
    assert "from seed_prompt, goal and behavior_guidance alike" in prompt
    assert "Keep its wording, tone and difficulty." in prompt
    assert "is a fact, not a reading" in prompt
    assert "give each without saying which is right" in prompt
    assert "Never cite a call whose arguments name a saved file" in prompt
    assert "Keep how the user answers questions the agent may ask them." in prompt
    assert "A call that returned nothing is not a refusal" in prompt
    assert "quote it word for word instead of paraphrasing it" in prompt
    assert "Before you add a look-alike of something" in prompt
    assert "encodes no meaning" in prompt


@pytest.mark.parametrize(
    "answer_style", ["reply_json", "structured_output", "submit_result"]
)
def test_system_prompt_keeps_cases_whose_named_things_or_situation_are_missing(
    answer_style,
):
    prompt = system_prompt(answer_style=answer_style)
    assert (
        "When one isn't there, that is not a reason to drop the case. Use one of the "
        "same kind that the environment has, or add one with setup"
    ) in prompt
    assert (
        "Drop for no_fit only when nothing of that kind exists and setup can't add it."
    ) in prompt
    assert (
        "Keep the situation the scenario describes: when something happened, whose it "
        "is, what state it is in."
    ) in prompt
    assert (
        "Before you drop a case for no_fit or rehearsal_failed, try at least one other way"
    ) in prompt
    assert prompt.index("Keep the situation") < prompt.index("Steps:\n1.")


def test_follow_up_message_per_answer_style():
    assert follow_up_message("bad JSON", "reply_json") == (
        "Your last reply could not be used: bad JSON\n\n"
        "Reply with only the JSON object your instructions describe, and nothing else."
    )
    assert follow_up_message("bad JSON", "structured_output") == follow_up_message(
        "bad JSON", "reply_json"
    )
    assert follow_up_message("You ended early.", "submit_result") == (
        "You ended early.\n\nCall submit_result with your result now. Your other "
        "tools are closed."
    )


@pytest.mark.parametrize("mode", ["multi_turn", "single_turn"])
def test_both_prompts_ask_for_a_clean_last_episode_and_a_reply(mode):
    prompt = system_prompt(mode=mode, rehearse=True)
    assert "Call start_episode one last time" in prompt
    assert "use that environment for the rehearsal only" in prompt
    assert "nothing to look around or to check your own work" in prompt
    assert "observe the result with read_state, which is not part of the rehearsal" in (
        prompt
    )
    assert "Then write rehearsal_reply" in prompt
    assert "the one you rehearsed in" in prompt
    assert "Don't reset after rehearsing" in prompt
    assert "Make that the environment you found the facts in" not in prompt
    assert '"rehearsal_reply": "' in prompt
    assert "rehearsal_reply and reference" in prompt


PROMPT_SHA256_AT_EB5647E64 = {
    (
        "multi_turn",
        "reply_json",
    ): "89e78a2189c88434d1356901418021826e200bc0198b1ceaf49f5a9b169d4860",
    (
        "multi_turn",
        "structured_output",
    ): "071913f69bc6107391e97db5b5d684108092633d12e227c5645fe5f2943b8bec",
    (
        "multi_turn",
        "submit_result",
    ): "69a67cf1309a0f560e7c56401dc72a5092a4ef400f04fac204dfa1925d1f674d",
    (
        "single_turn",
        "reply_json",
    ): "73ce265d3ddaf29cddfbc4a9323f28887a348cbf62fe4fe5aa8c0851d6565c3d",
    (
        "single_turn",
        "structured_output",
    ): "fccdc6e202029c1d34989535a3cd6f5fbd057dd3cbe6debfbdaf70e3b9d69991",
    (
        "single_turn",
        "submit_result",
    ): "4d31293c2db525c02e470b745fbdd6b5803dd9d41a04575b5afab8b5d65924f7",
}
"""SHA-256 of each default prompt at commit eb5647e64, before the rehearsal check and
the turn limit."""


@pytest.mark.parametrize(("mode", "answer_style"), PROMPT_SHA256_AT_EB5647E64)
def test_without_a_rehearsal_or_one_turn_the_prompt_is_as_before(mode, answer_style):
    """With no rehearsal judge and no one-message limit, grounding is told exactly
    what it was told before either existed. Update a digest only on a deliberate
    change to the prompt."""
    prompt = system_prompt(answer_style=answer_style, mode=mode)
    assert (
        hashlib.sha256(prompt.encode()).hexdigest()
        == PROMPT_SHA256_AT_EB5647E64[(mode, answer_style)]
    )
    assert "rehearsal_reply" not in prompt
    assert "turn_limit" not in prompt
