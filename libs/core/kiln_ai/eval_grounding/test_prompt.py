import json
import re

import pytest

from kiln_ai.eval_grounding.models import EvalContext, GroundingCase, GroundingResult
from kiln_ai.eval_grounding.prompt import case_message, system_prompt
from kiln_ai.eval_grounding.session import (
    READ_STATE_TOOL,
    START_EPISODE_TOOL,
    GroundingLimits,
)

CASE = GroundingCase(
    scenario="A technician asks to put one of their open work orders on hold.",
    seed_prompt="Can you put my pump job on hold?",
    synthetic_user_info="<persona>A technician</persona>\n<goal>Hold the job</goal>\n",
)

EVAL_CONTEXT = EvalContext(
    specification="The agent puts work orders on hold only when asked.",
    target_task_prompt="Help technicians manage their work orders.",
    data_guide="Technicians in the field, often on a phone.\n",
)

TARGET_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_work_orders",
            "description": "List work orders.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_work_order",
            "description": "Change a work order.",
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
        readme="# Server\nStart from a fixture.\n",
        target_tools=TARGET_TOOLS,
    )
    assert message == (
        "<specification>\n"
        "The agent puts work orders on hold only when asked.\n"
        "</specification>\n\n"
        "<target_task_prompt>\n"
        "Help technicians manage their work orders.\n"
        "</target_task_prompt>\n\n"
        "<data_guide>\nTechnicians in the field, often on a phone.\n</data_guide>\n\n"
        "<case_scenario>\n"
        "A technician asks to put one of their open work orders on hold.\n"
        "</case_scenario>\n\n"
        "<simulated_user>\n"
        "<seed_prompt>\nCan you put my pump job on hold?\n</seed_prompt>\n"
        "<persona>A technician</persona>\n<goal>Hold the job</goal>\n"
        "</simulated_user>\n\n"
        f"<reset_schema>\n{json.dumps(schema, indent=2)}\n</reset_schema>\n\n"
        "<server_readme>\n# Server\nStart from a fixture.\n</server_readme>\n\n"
        "<target_tools>\n"
        "- list_work_orders: List work orders.\n"
        "- update_work_order: Change a work order.\n"
        "</target_tools>"
    )


@pytest.mark.parametrize("data_guide", [None, "", "  "])
def test_case_message_without_data_guide_schema_readme_or_tools(data_guide):
    message = case_message(
        CASE,
        eval_context=EVAL_CONTEXT.model_copy(update={"data_guide": data_guide}),
        reset_schema=None,
        readme=None,
        target_tools=[],
    )
    assert message.startswith("<specification>\n")
    assert "<data_guide>" not in message
    assert (
        "<reset_schema>\nThe server publishes no reset schema. "
        "Call start_episode with {}.\n</reset_schema>"
    ) in message
    assert "<server_readme>\n\n</server_readme>" in message
    assert "<target_tools>\nNone.\n</target_tools>" in message


def test_system_prompt_states_the_limits():
    prompt = system_prompt(GroundingLimits(max_tool_calls=12, max_resets=3), 300)
    assert "Limits: 3 resets, 12 tool calls, 5 minutes." in prompt


def test_system_prompt_names_the_tools_and_every_result_field():
    prompt = system_prompt()
    assert "Limits: 10 resets, 40 tool calls, 15 minutes." in prompt
    for tool in (START_EPISODE_TOOL, READ_STATE_TOOL):
        assert f"{tool}(" in prompt
    for field in GroundingResult.model_fields:
        assert f'"{field}"' in prompt
    for reason in ("no_fit", "unrepresentable", "rehearsal_failed"):
        assert reason in prompt


def test_system_prompt_lists_every_case_message_section():
    message = case_message(
        CASE, eval_context=EVAL_CONTEXT, reset_schema=None, readme=None, target_tools=[]
    )
    prompt = system_prompt()
    for tag in re.findall(r"^<(\w+)>$", message, flags=re.MULTILINE):
        if tag != "seed_prompt":
            assert f"\n<{tag}> " in prompt
