"""The grounding prototype command, with kiln_server's clients and `claude` stubbed."""

import asyncio
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.openenv import OpenEnvReset
from kiln_ai.datamodel.task import Task
from kiln_ai.eval_grounding.batch import (
    CaseGrounded,
    GroundingCaseError,
    GroundingFinished,
)
from kiln_ai.eval_grounding.models import (
    DropReason,
    EvalContext,
    GroundingOutcome,
    GroundingResult,
    LoggedCall,
)
from kiln_ai.eval_grounding.prompt import system_prompt
from kiln_ai.openenv.reset_schema_brief import RESET_ARGUMENTS_FRAMING
from kiln_ai.openenv.session_manager import OpenEnvTransientError
from kiln_ai.utils.usage import Usage

from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    SyntheticUserCase,
)
from app.desktop.studio_server.batch_plan_api import BatchPlanApiOutput
from app.desktop.studio_server.dev import ground_cases, grounding_mcp
from app.desktop.studio_server.dev.ground_cases import (
    DATA_GUIDE_FRAMING,
    DEFAULT_CLAUDE_MODEL,
    CaseRun,
    ClaudeReply,
    ClaudeRunError,
    GroundingSetupError,
    PrepareArgs,
    claude_md_files_above,
    compose_guidance,
    load_prepared,
    main,
    parse_case_indices,
    parse_grounding_result,
    prepare,
    run_claude,
    summarize,
)
from app.desktop.studio_server.dev.grounding_mcp import GroundingRunLog

PREPARED_SCHEMA = {"type": "object", "properties": {"level": {"type": "integer"}}}
PREPARED_README = "Prepared readme."
PREPARED_SPEC = "The agent adds only the note the member asks for."

USER_INFO = "<persona>Sam, a member</persona><goal>Add a note</goal>"

GROUNDED_REPLY = {
    "status": "grounded",
    "drop_reason": None,
    "drop_detail": None,
    "seed_prompt": "Add the note 'hi' please",
    "synthetic_user_info": USER_INFO,
    "reference": {
        "starting_point": "No notes yet.",
        "facts": [
            {
                "text": "There are no notes.",
                "evidence": {
                    "tool": "read_notes",
                    "args": {},
                    "result_excerpt": "[]",
                },
            }
        ],
        "expected_outcome": "A note 'hi' exists, and no other note was added.",
    },
}

DROPPED_REPLY = {
    "status": "dropped",
    "drop_reason": "no_fit",
    "drop_detail": "No starting state has notes.",
}


# ---- prepare ----


def test_compose_guidance_orders_the_sections():
    guidance = compose_guidance("Base guidance.\n", "BRIEF", "  Members add notes. ")
    assert guidance == (
        "Base guidance.\n\nBRIEF\n\n"
        f"{DATA_GUIDE_FRAMING}\n\n<data_guide>\nMembers add notes.\n</data_guide>"
    )


@pytest.mark.parametrize("data_guide", [None, "", "   "])
def test_compose_guidance_leaves_out_empty_parts(data_guide):
    assert compose_guidance("Base.", None, data_guide) == "Base."


@pytest.fixture
def task(project):
    t = Task(name="agent", instruction="Help members with notes.", parent=project)
    t.save_to_file()
    return t


@pytest.fixture
def inputs(tmp_path):
    (tmp_path / "spec.txt").write_text("The agent adds notes correctly.")
    (tmp_path / "guidance.txt").write_text("Plan multi-turn cases.")
    (tmp_path / "data_guide.txt").write_text("Members ask to add notes.")
    return tmp_path


def sdk_case(index: int) -> SyntheticUserCase:
    return SyntheticUserCase(
        seed_prompt=f"hello {index}",
        synthetic_user_info=USER_INFO,
        scenario_index=index,
    )


@pytest.fixture
def kiln_server_stubs():
    """The batch planner and the simulated-user client, as kiln_server would answer.
    Each chunk's cases are numbered from 0, as kiln_server numbers them."""
    plan = AsyncMock(
        return_value=BatchPlanApiOutput(
            prompts=[f"scenario {i}" for i in range(23)], summary="a plan"
        )
    )
    client = Mock()
    client.generate = AsyncMock(
        side_effect=lambda **kwargs: [
            sdk_case(i) for i in range(len(kwargs["case_scenarios"]))
        ]
    )
    client_class = Mock(return_value=client)
    with (
        patch.object(ground_cases, "_run_batch_plan_kiln_server", plan),
        patch.object(ground_cases, "SyntheticUserClient", client_class),
    ):
        yield plan, client_class, client


async def test_prepare_writes_every_input(
    project,
    task,
    openenv_server,
    inputs,
    kiln_server_stubs,
    tmp_path,
    reset_schema,
    server_readme,
):
    plan, client_class, client = kiln_server_stubs
    out = tmp_path / "prepared"
    await prepare(
        PrepareArgs(
            project=project.path,
            task_id=str(task.id),
            openenv_server_id=str(openenv_server.id),
            spec=inputs / "spec.txt",
            base_guidance=inputs / "guidance.txt",
            data_guide=inputs / "data_guide.txt",
            count=23,
            out=out,
        ),
        copilot_api_key="key",
    )

    assert json.loads((out / "schema.json").read_text()) == reset_schema
    metadata = json.loads((out / "metadata.json").read_text())
    assert metadata["readme_content"] == server_readme
    brief = (out / "brief.txt").read_text()
    assert brief.startswith(RESET_ARGUMENTS_FRAMING)
    assert "- fixture_id: The starting data." in brief
    assert "- seed" not in brief

    guidance = (out / "guidance.txt").read_text()
    assert guidance == compose_guidance(
        "Plan multi-turn cases.", brief, "Members ask to add notes."
    )
    plan.assert_awaited_once_with(
        task_prompt="Help members with notes.",
        task_input_schema=None,
        task_output_schema=None,
        input_data_guide=None,
        user_guidance=guidance,
        count=23,
    )
    assert json.loads((out / "plan.json").read_text())["prompts"][22] == "scenario 22"

    client_class.assert_called_once_with(api_key="key")
    chunks = [call.kwargs["case_scenarios"] for call in client.generate.await_args_list]
    assert [len(chunk) for chunk in chunks] == [20, 3]
    assert chunks[1][0] == "scenario 20"
    assert client.generate.await_args_list[0].kwargs["target_specification"] == (
        "The agent adds notes correctly."
    )
    users = json.loads((out / "users.json").read_text())
    assert [u["scenario_index"] for u in users] == list(range(23))

    assert load_prepared(out).eval_context == EvalContext(
        specification="The agent adds notes correctly.",
        target_task_prompt="Help members with notes.",
        data_guide="Members ask to add notes.",
    )


def prepare_args(project, task, openenv_server, inputs, out, data_guide=None):
    return PrepareArgs(
        project=project.path,
        task_id=str(task.id),
        openenv_server_id=str(openenv_server.id),
        spec=inputs / "spec.txt",
        base_guidance=inputs / "guidance.txt",
        data_guide=data_guide,
        count=2,
        out=out,
    )


@pytest.mark.parametrize("guide_text", [None, "  \n"])
async def test_prepare_without_a_data_guide_removes_an_earlier_one(
    project, task, openenv_server, inputs, kiln_server_stubs, tmp_path, guide_text
):
    guide_path = None
    if guide_text is not None:
        guide_path = inputs / "blank_guide.txt"
        guide_path.write_text(guide_text)
    out = tmp_path / "prepared"
    out.mkdir()
    (out / "data_guide.txt").write_text("From an earlier run.")
    await prepare(
        prepare_args(project, task, openenv_server, inputs, out, guide_path),
        copilot_api_key="key",
    )
    assert not (out / "data_guide.txt").exists()
    assert load_prepared(out).eval_context.data_guide is None


async def test_a_failed_prepare_rerun_leaves_a_folder_ground_refuses(
    project, task, openenv_server, inputs, kiln_server_stubs, tmp_path
):
    out = tmp_path / "prepared"
    await prepare(
        prepare_args(project, task, openenv_server, inputs, out),
        copilot_api_key="key",
    )
    plan, _, _ = kiln_server_stubs
    plan.side_effect = RuntimeError("planner down")
    with pytest.raises(RuntimeError, match="planner down"):
        await prepare(
            prepare_args(project, task, openenv_server, inputs, out),
            copilot_api_key="key",
        )
    with pytest.raises(GroundingSetupError, match=r"missing plan\.json, users\.json"):
        load_prepared(out)


def test_prepare_from_the_command_line_reports_a_missing_key(
    project, task, openenv_server, inputs, tmp_path, capsys
):
    from fastapi import HTTPException

    with patch.object(
        ground_cases,
        "get_copilot_api_key",
        Mock(side_effect=HTTPException(status_code=401, detail="No key.")),
    ):
        code = main(
            [
                "prepare",
                "--project",
                str(project.path),
                "--task-id",
                str(task.id),
                "--openenv-server-id",
                str(openenv_server.id),
                "--spec",
                str(inputs / "spec.txt"),
                "--base-guidance",
                str(inputs / "guidance.txt"),
                "--count",
                "2",
                "--out",
                str(tmp_path / "prepared"),
            ]
        )
    assert code == 1
    assert "No key." in capsys.readouterr().err


async def test_prepare_with_an_unknown_task(project, openenv_server, inputs, tmp_path):
    with pytest.raises(GroundingSetupError, match="no task with id nope"):
        await prepare(
            PrepareArgs(
                project=project.path,
                task_id="nope",
                openenv_server_id=str(openenv_server.id),
                spec=inputs / "spec.txt",
                base_guidance=inputs / "guidance.txt",
                data_guide=None,
                count=1,
                out=tmp_path / "prepared",
            ),
            copilot_api_key="key",
        )


# ---- reading prepare's output ----


def write_prepared(folder: Path, case_count: int = 2) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "specification.txt").write_text(PREPARED_SPEC)
    (folder / "task_prompt.txt").write_text("Help members with notes.")
    (folder / "data_guide.txt").write_text("Members ask to add notes.")
    (folder / "schema.json").write_text(json.dumps(PREPARED_SCHEMA))
    (folder / "metadata.json").write_text(
        json.dumps({"name": "n", "readme_content": PREPARED_README})
    )
    (folder / "brief.txt").write_text("brief")
    (folder / "guidance.txt").write_text("guidance")
    (folder / "plan.json").write_text(
        json.dumps(
            {"prompts": [f"scenario {i}" for i in range(case_count)], "summary": "s"}
        )
    )
    # Users come back in a different order from the plan; scenario_index joins them.
    users = [
        {
            "seed_prompt": f"hello {i}",
            "synthetic_user_info": USER_INFO,
            "scenario_index": i,
        }
        for i in reversed(range(case_count))
    ]
    (folder / "users.json").write_text(json.dumps(users))
    return folder


def test_load_prepared_joins_users_to_their_scenarios(tmp_path):
    prepared = load_prepared(write_prepared(tmp_path / "in"))
    assert [(c.scenario, c.seed_prompt) for c in prepared.cases] == [
        ("scenario 1", "hello 1"),
        ("scenario 0", "hello 0"),
    ]
    assert prepared.reset_schema == PREPARED_SCHEMA
    assert prepared.readme == PREPARED_README
    assert prepared.eval_context == EvalContext(
        specification=PREPARED_SPEC,
        target_task_prompt="Help members with notes.",
        data_guide="Members ask to add notes.",
    )


@pytest.mark.parametrize("name", ["users.json", "specification.txt", "task_prompt.txt"])
def test_load_prepared_names_missing_files(tmp_path, name):
    folder = write_prepared(tmp_path / "in")
    (folder / name).unlink()
    with pytest.raises(GroundingSetupError, match=rf"missing {re.escape(name)}\."):
        load_prepared(folder)


@pytest.mark.parametrize("guide_text", [None, " \n\t"])
def test_load_prepared_without_a_data_guide(tmp_path, guide_text):
    folder = write_prepared(tmp_path / "in")
    if guide_text is None:
        (folder / "data_guide.txt").unlink()
    else:
        (folder / "data_guide.txt").write_text(guide_text)
    assert load_prepared(folder).eval_context.data_guide is None


def test_parse_case_indices():
    assert parse_case_indices(None, 3) == [0, 1, 2]
    assert parse_case_indices("4, 0-2,1", 5) == [0, 1, 2, 4]
    with pytest.raises(GroundingSetupError, match="not an index"):
        parse_case_indices("a", 5)
    with pytest.raises(GroundingSetupError, match=r"\[5\] out of range"):
        parse_case_indices("5", 5)


# ---- parsing the agent's reply ----


@pytest.mark.parametrize(
    "text",
    [
        json.dumps(GROUNDED_REPLY),
        f"```json\n{json.dumps(GROUNDED_REPLY)}\n```",
        f"Here is the result:\n{json.dumps(GROUNDED_REPLY)}\nDone.",
    ],
)
def test_parse_grounding_result_finds_the_object(text):
    assert parse_grounding_result(text).status == "grounded"


@pytest.mark.parametrize(
    "text",
    ["no json here", "{not json}", json.dumps({**GROUNDED_REPLY, "reference": None})],
)
def test_parse_grounding_result_rejects_unusable_replies(text):
    with pytest.raises(ValueError):
        parse_grounding_result(text)


# ---- ground --engine claude ----


def logged(tool: str) -> LoggedCall:
    return LoggedCall(tool=tool, args={}, output="ok", is_error=False, episode_id="ep")


def run_log(**overrides: Any) -> GroundingRunLog:
    fields: dict[str, Any] = {
        "call_log": [logged("start_episode"), logged("read_notes")],
        "last_reset": OpenEnvReset(
            openenv_server_id="srv", reset_kwargs={"fixture_id": "beta"}
        ),
        **overrides,
    }
    return GroundingRunLog(**fields)


def reply(result: Any, *, session_id: str | None = "session-1", cost: float = 0.5):
    text = result if isinstance(result, str) else json.dumps(result)
    return ClaudeReply(
        result=text,
        session_id=session_id,
        usage=Usage(input_tokens=100, output_tokens=10, total_tokens=110, cost=cost),
        raw=json.dumps({"result": text}),
    )


class FakeClaude:
    """Stands in for `claude -p`: writes the run log where the MCP config says the
    grounding server would, and answers with fixed replies in order."""

    def __init__(
        self,
        replies: list[ClaudeReply | BaseException],
        log: GroundingRunLog | None = None,
    ) -> None:
        self.replies = list(replies)
        self.log = log if log is not None else run_log()
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, argv, *, stdin, cwd, timeout_s):
        self.calls.append(
            {"argv": list(argv), "stdin": stdin, "cwd": cwd, "timeout_s": timeout_s}
        )
        if "--mcp-config" in argv:
            config_path = Path(argv[argv.index("--mcp-config") + 1])
            config = json.loads(config_path.read_text())
            server_args = config["mcpServers"]["grounding"]["args"]
            log_path = Path(server_args[server_args.index("--log-out") + 1])
            log_path.write_text(self.log.model_dump_json())
        answer = self.replies.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


def ground_argv(project, openenv_server, in_dir: Path, out: Path, *extra: str):
    return [
        "ground",
        "--project",
        str(project.path),
        "--openenv-server-id",
        str(openenv_server.id),
        "--in",
        str(in_dir),
        "--out",
        str(out),
        "--engine",
        "claude",
        *extra,
    ]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


@pytest.fixture
def prepared_dir(tmp_path):
    return write_prepared(tmp_path / "in", case_count=1)


def test_ground_takes_the_reset_from_the_session_log(
    project, openenv_server, prepared_dir, tmp_path
):
    fake = FakeClaude([reply(GROUNDED_REPLY)])
    out = tmp_path / "run"
    code = main(
        ground_argv(project, openenv_server, prepared_dir, out),
        claude_runner=fake,
    )
    assert code == 0

    [outcome] = read_json(out / "outcomes.json")
    assert outcome["case_index"] == 0
    assert outcome["outcome"]["status"] == "grounded"
    assert outcome["outcome"]["openenv_reset"]["reset_kwargs"] == {"fixture_id": "beta"}
    assert outcome["outcome"]["seed_prompt"] == "Add the note 'hi' please"
    assert [c["tool"] for c in outcome["outcome"]["call_log"]] == [
        "start_episode",
        "read_notes",
    ]

    summary = read_json(out / "summary.json")
    assert summary["engine"] == "claude"
    assert summary["model"] == DEFAULT_CLAUDE_MODEL
    assert (summary["grounded"], summary["dropped"]) == (1, 0)
    assert summary["grounded_resets"] == [
        {"case_index": 0, "reset_kwargs": {"fixture_id": "beta"}}
    ]
    assert summary["usage"]["cost"] == 0.5
    assert (out / "system_prompt.txt").read_text() == system_prompt()


def test_ground_runs_claude_with_only_the_grounding_tools(
    project, openenv_server, prepared_dir, tmp_path
):
    fake = FakeClaude([reply(GROUNDED_REPLY)])
    out = tmp_path / "run"
    main(
        ground_argv(
            project, openenv_server, prepared_dir, out, "--model", "some-model"
        ),
        claude_runner=fake,
    )
    [call] = fake.calls
    argv = call["argv"]
    case_dir = out / "case_000"
    assert argv[:2] == ["claude", "-p"]
    assert argv[argv.index("--model") + 1] == "some-model"
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--allowedTools") + 1] == "mcp__grounding__*"
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert argv[argv.index("--system-prompt") + 1] == system_prompt()
    assert "--strict-mcp-config" in argv
    assert "--bare" not in argv
    assert call["cwd"] == case_dir
    assert call["timeout_s"] > 0

    assert call["stdin"] == (case_dir / "message.txt").read_text()
    assert call["stdin"].startswith(
        f"<specification>\n{PREPARED_SPEC}\n</specification>"
    )
    assert "<data_guide>\nMembers ask to add notes.\n</data_guide>" in call["stdin"]
    assert "<case_scenario>\nscenario 0\n</case_scenario>" in call["stdin"]
    assert "- append_note:" in call["stdin"]
    assert PREPARED_README in call["stdin"]

    config = read_json(Path(argv[argv.index("--mcp-config") + 1]))
    server = config["mcpServers"]["grounding"]
    assert server["command"] == sys.executable
    assert server["args"][0] == str(grounding_mcp.script_path())
    assert server["args"][server["args"].index("--project") + 1] == str(
        project.path.resolve()
    )
    assert server["args"][server["args"].index("--log-out") + 1] == str(
        (case_dir / "run_log.json").resolve()
    )


def test_ground_passes_the_thinking_level_as_claude_effort(
    project, openenv_server, prepared_dir, tmp_path
):
    fake = FakeClaude([reply(GROUNDED_REPLY)])
    main(
        ground_argv(
            project,
            openenv_server,
            prepared_dir,
            tmp_path / "run",
            "--thinking-level",
            "xhigh",
        ),
        claude_runner=fake,
    )
    argv = fake.calls[0]["argv"]
    assert argv[argv.index("--effort") + 1] == "xhigh"


def test_ground_without_a_thinking_level_leaves_claude_effort_alone(
    project, openenv_server, prepared_dir, tmp_path
):
    fake = FakeClaude([reply(GROUNDED_REPLY)])
    main(
        ground_argv(project, openenv_server, prepared_dir, tmp_path / "run"),
        claude_runner=fake,
    )
    assert "--effort" not in fake.calls[0]["argv"]


def test_cited_tools_lose_the_grounding_servers_prefix(
    project, openenv_server, prepared_dir, tmp_path
):
    prefixed = json.loads(json.dumps(GROUNDED_REPLY))
    prefixed["reference"]["facts"][0]["evidence"]["tool"] = "mcp__grounding__read_notes"
    out = tmp_path / "run"
    main(
        ground_argv(project, openenv_server, prepared_dir, out),
        claude_runner=FakeClaude([reply(prefixed)]),
    )
    [outcome] = read_json(out / "outcomes.json")
    [fact] = outcome["outcome"]["reference"]["facts"]
    assert fact["evidence"]["tool"] == "read_notes"


def test_run_config_id_needs_a_task_id(project, openenv_server, prepared_dir, tmp_path):
    code = main(
        ground_argv(
            project,
            openenv_server,
            prepared_dir,
            tmp_path / "run",
            "--run-config-id",
            "rc1",
        ),
        claude_runner=FakeClaude([]),
    )
    assert code == 1


def test_ground_uses_a_prompt_file_and_bare_mode(
    project, openenv_server, prepared_dir, tmp_path
):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Try this prompt.")
    fake = FakeClaude([reply(GROUNDED_REPLY)])
    main(
        ground_argv(
            project,
            openenv_server,
            prepared_dir,
            tmp_path / "run",
            "--prompt",
            str(prompt),
            "--claude-bare",
            "--claude-bin",
            "/opt/claude",
        ),
        claude_runner=fake,
    )
    argv = fake.calls[0]["argv"]
    assert argv[0] == "/opt/claude"
    assert argv[argv.index("--system-prompt") + 1] == "Try this prompt."
    assert "--bare" in argv


def test_ground_records_a_model_drop(project, openenv_server, prepared_dir, tmp_path):
    out = tmp_path / "run"
    main(
        ground_argv(project, openenv_server, prepared_dir, out),
        claude_runner=FakeClaude([reply(DROPPED_REPLY)]),
    )
    [outcome] = read_json(out / "outcomes.json")
    assert outcome["outcome"]["drop_reason"] == "no_fit"
    summary = read_json(out / "summary.json")
    assert summary["drops_by_reason"] == {"no_fit": 1}
    assert summary["grounded_resets"] == []


def test_a_limit_stop_is_a_limit_drop(project, openenv_server, prepared_dir, tmp_path):
    out = tmp_path / "run"
    fake = FakeClaude(
        [reply(GROUNDED_REPLY)],
        log=run_log(stopped="limit", stop_detail="Kept calling tools."),
    )
    main(ground_argv(project, openenv_server, prepared_dir, out), claude_runner=fake)
    [outcome] = read_json(out / "outcomes.json")
    assert outcome["outcome"]["drop_reason"] == DropReason.limit.value
    assert outcome["outcome"]["drop_detail"] == "Kept calling tools."


def test_a_timeout_is_a_limit_drop(project, openenv_server, prepared_dir, tmp_path):
    out = tmp_path / "run"
    main(
        ground_argv(project, openenv_server, prepared_dir, out),
        claude_runner=FakeClaude([TimeoutError()]),
    )
    [outcome] = read_json(out / "outcomes.json")
    assert outcome["outcome"]["drop_reason"] == "limit"
    assert "minute limit" in outcome["outcome"]["drop_detail"]
    assert len(outcome["outcome"]["call_log"]) == 2
    assert outcome["outcome"]["usage_complete"] is False
    assert read_json(out / "summary.json")["cases_with_incomplete_usage"] == 1


def test_an_unusable_reply_is_retried_once_then_dropped(
    project, openenv_server, prepared_dir, tmp_path
):
    out = tmp_path / "run"
    fake = FakeClaude([reply("not json"), reply("still not json", cost=0.25)])
    main(ground_argv(project, openenv_server, prepared_dir, out), claude_runner=fake)

    retry = fake.calls[1]
    assert retry["argv"][retry["argv"].index("--resume") + 1] == "session-1"
    assert "--mcp-config" not in retry["argv"]
    assert "--strict-mcp-config" in retry["argv"]
    assert retry["argv"][retry["argv"].index("--tools") + 1] == ""
    assert "could not be used" in retry["stdin"]

    [outcome] = read_json(out / "outcomes.json")
    assert outcome["outcome"]["drop_reason"] == "invalid_output"
    assert outcome["outcome"]["usage"]["cost"] == 0.75
    assert (out / "case_000" / "claude_retry_output.json").exists()


def test_a_retry_that_parses_grounds_the_case(
    project, openenv_server, prepared_dir, tmp_path
):
    out = tmp_path / "run"
    fake = FakeClaude([reply("oops"), reply(GROUNDED_REPLY)])
    main(ground_argv(project, openenv_server, prepared_dir, out), claude_runner=fake)
    [outcome] = read_json(out / "outcomes.json")
    assert outcome["outcome"]["status"] == "grounded"
    assert outcome["outcome"]["openenv_reset"]["reset_kwargs"] == {"fixture_id": "beta"}


def test_an_unusable_reply_without_a_session_is_dropped_without_retry(
    project, openenv_server, prepared_dir, tmp_path
):
    out = tmp_path / "run"
    fake = FakeClaude([reply("oops", session_id=None)])
    main(ground_argv(project, openenv_server, prepared_dir, out), claude_runner=fake)
    assert len(fake.calls) == 1
    [outcome] = read_json(out / "outcomes.json")
    assert outcome["outcome"]["drop_reason"] == "invalid_output"


def test_grounded_without_a_reset_is_dropped(
    project, openenv_server, prepared_dir, tmp_path
):
    out = tmp_path / "run"
    fake = FakeClaude([reply(GROUNDED_REPLY)], log=run_log(last_reset=None))
    main(ground_argv(project, openenv_server, prepared_dir, out), claude_runner=fake)
    [outcome] = read_json(out / "outcomes.json")
    assert outcome["outcome"]["drop_reason"] == "invalid_output"


def test_failed_cases_are_reported_and_the_rest_carry_on(
    project, openenv_server, tmp_path, capsys
):
    in_dir = write_prepared(tmp_path / "in", case_count=3)
    out = tmp_path / "run"
    replies = {
        "case_000": ClaudeRunError("claude exited with code 1: auth"),
        "case_001": reply(GROUNDED_REPLY),
        "case_002": reply(GROUNDED_REPLY),
    }
    error_log = run_log(stopped="error", stop_detail="server unreachable")

    async def runner(argv, *, stdin, cwd, timeout_s):
        if cwd.name == "case_002":
            return await FakeClaude([replies["case_002"]], log=error_log)(
                argv, stdin=stdin, cwd=cwd, timeout_s=timeout_s
            )
        return await FakeClaude([replies[cwd.name]])(
            argv, stdin=stdin, cwd=cwd, timeout_s=timeout_s
        )

    code = main(ground_argv(project, openenv_server, in_dir, out), claude_runner=runner)

    assert code == 1
    summary = read_json(out / "summary.json")
    assert summary["cases"] == 3
    assert summary["grounded"] == 1
    assert [f["case_index"] for f in summary["failed_cases"]] == [0, 2]
    assert "auth" in summary["failed_cases"][0]["error"]
    assert "server unreachable" in summary["failed_cases"][1]["error"]
    assert [o["case_index"] for o in read_json(out / "outcomes.json")] == [1]
    assert "case 0: failed" in capsys.readouterr().err


def test_a_missing_run_log_fails_the_case(
    project, openenv_server, prepared_dir, tmp_path
):
    async def runner(argv, *, stdin, cwd, timeout_s):
        return reply(GROUNDED_REPLY)

    out = tmp_path / "run"
    code = main(
        ground_argv(project, openenv_server, prepared_dir, out), claude_runner=runner
    )
    assert code == 1
    [failed] = read_json(out / "summary.json")["failed_cases"]
    assert "never started" in failed["error"]


def test_a_corrupt_run_log_fails_the_case(
    project, openenv_server, prepared_dir, tmp_path
):
    async def runner(argv, *, stdin, cwd, timeout_s):
        config = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())
        server_args = config["mcpServers"]["grounding"]["args"]
        Path(server_args[server_args.index("--log-out") + 1]).write_text("{")
        return reply(GROUNDED_REPLY)

    out = tmp_path / "run"
    code = main(
        ground_argv(project, openenv_server, prepared_dir, out), claude_runner=runner
    )
    assert code == 1
    [failed] = read_json(out / "summary.json")["failed_cases"]
    assert "is not valid" in failed["error"]


def test_ground_runs_only_the_chosen_cases(project, openenv_server, tmp_path):
    in_dir = write_prepared(tmp_path / "in", case_count=4)
    out = tmp_path / "run"

    async def runner(argv, *, stdin, cwd, timeout_s):
        return await FakeClaude([reply(DROPPED_REPLY)])(
            argv, stdin=stdin, cwd=cwd, timeout_s=timeout_s
        )

    main(
        ground_argv(project, openenv_server, in_dir, out, "--cases", "1,3"),
        claude_runner=runner,
    )
    assert sorted(p.name for p in out.glob("case_*")) == ["case_001", "case_003"]


# ---- ground --engine kiln ----


def kiln_argv(project, openenv_server, in_dir: Path, out: Path, *extra: str):
    argv = ground_argv(project, openenv_server, in_dir, out, *extra)
    argv[argv.index("claude")] = "kiln"
    return argv


def grounded_outcome() -> GroundingOutcome:
    return GroundingOutcome.from_result(
        GroundingResult.model_validate(GROUNDED_REPLY),
        openenv_reset=OpenEnvReset(
            openenv_server_id="srv", reset_kwargs={"fixture_id": "beta"}
        ),
        call_log=[logged("start_episode")],
        usage=Usage(input_tokens=100, output_tokens=10, total_tokens=110, cost=0.25),
    )


class FakeGroundCases:
    """Stands in for `ground_cases`: grounds every case it is given, in reverse order,
    or raises `error` after the first."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, cases, **kwargs):
        self.calls.append({"cases": list(cases), **kwargs})
        for position in reversed(range(len(cases))):
            yield CaseGrounded(position, grounded_outcome())
            if self.error is not None:
                raise self.error
        yield GroundingFinished(
            grounded=len(cases), dropped=0, usage=None, usage_complete=True
        )


def test_engine_kiln_grounds_through_ground_cases(project, openenv_server, tmp_path):
    in_dir = write_prepared(tmp_path / "in", case_count=4)
    out = tmp_path / "run"
    fake = FakeGroundCases()
    with patch.object(ground_cases, "ground_cases", fake):
        code = main(
            kiln_argv(
                project,
                openenv_server,
                in_dir,
                out,
                "--model",
                "gpt-4",
                "--provider",
                "openai",
                "--answer-style",
                "submit_result",
                "--cases",
                "1,3",
            )
        )

    assert code == 0
    [call] = fake.calls
    # Case indices count users.json, which write_prepared writes in reverse plan order.
    assert [c.scenario for c in call["cases"]] == ["scenario 2", "scenario 0"]
    assert call["model_name"] == "gpt-4"
    assert call["model_provider"] == ModelProviderName.openai
    assert call["answer_style"] == "submit_result"
    assert call["eval_context"].specification == PREPARED_SPEC
    assert call["system_prompt_text"] == system_prompt(answer_style="submit_result")
    assert [t["function"]["name"] for t in call["target_tools"]] == [
        "append_note",
        "read_notes",
        "explode",
        "sleep",
    ]
    assert (out / "system_prompt.txt").read_text() == call["system_prompt_text"]
    outcomes = read_json(out / "outcomes.json")
    assert [o["case_index"] for o in outcomes] == [1, 3]
    summary = read_json(out / "summary.json")
    assert summary["engine"] == "kiln"
    assert summary["model"] == "gpt-4"
    assert summary["provider"] == "openai"
    assert summary["answer_style"] == "submit_result"
    assert summary["error"] is None
    assert summary["grounded"] == 2
    assert summary["usage"]["cost"] == 0.5


def test_engine_kiln_defaults_to_structured_output(
    project, openenv_server, prepared_dir, tmp_path
):
    fake = FakeGroundCases()
    with patch.object(ground_cases, "ground_cases", fake):
        main(
            kiln_argv(
                project,
                openenv_server,
                prepared_dir,
                tmp_path / "run",
                "--model",
                "gpt-4",
                "--provider",
                "openai",
            )
        )
    assert fake.calls[0]["answer_style"] == "structured_output"
    assert fake.calls[0]["thinking_level"] is None


def test_engine_kiln_runs_at_the_thinking_level(
    project, openenv_server, prepared_dir, tmp_path
):
    fake = FakeGroundCases()
    with patch.object(ground_cases, "ground_cases", fake):
        main(
            kiln_argv(
                project,
                openenv_server,
                prepared_dir,
                tmp_path / "run",
                "--model",
                "gpt-4",
                "--provider",
                "openai",
                "--thinking-level",
                "high",
            )
        )
    assert fake.calls[0]["thinking_level"] == "high"


def test_an_error_from_ground_cases_keeps_the_outcomes_so_far(
    project, openenv_server, tmp_path, capsys
):
    in_dir = write_prepared(tmp_path / "in", case_count=3)
    out = tmp_path / "run"
    fake = FakeGroundCases(
        error=GroundingCaseError(
            1,
            KilnRunError(
                "Something went wrong.",
                partial_trace=None,
                original=OpenEnvTransientError("the environment went away"),
            ),
        )
    )
    with patch.object(ground_cases, "ground_cases", fake):
        code = main(
            kiln_argv(
                project,
                openenv_server,
                in_dir,
                out,
                "--model",
                "m",
                "--provider",
                "openai",
            )
        )

    assert code == 1
    assert [o["case_index"] for o in read_json(out / "outcomes.json")] == [2]
    summary = read_json(out / "summary.json")
    assert summary["error"] == (
        "case 1: OpenEnvTransientError: the environment went away"
    )
    assert summary["cases"] == 3
    assert "Grounding stopped: case 1: OpenEnvTransientError" in capsys.readouterr().err


@pytest.mark.parametrize("extra", [(), ("--model", "m"), ("--provider", "openai")])
def test_engine_kiln_needs_a_model_and_provider(
    project, openenv_server, prepared_dir, tmp_path, extra
):
    with pytest.raises(SystemExit):
        main(kiln_argv(project, openenv_server, prepared_dir, tmp_path / "run", *extra))


def test_answer_style_is_refused_for_engine_claude(
    project, openenv_server, prepared_dir, tmp_path
):
    with pytest.raises(SystemExit):
        main(
            ground_argv(
                project,
                openenv_server,
                prepared_dir,
                tmp_path / "run",
                "--answer-style",
                "submit_result",
            ),
            claude_runner=FakeClaude([]),
        )


def test_provider_is_refused_for_engine_claude(
    project, openenv_server, prepared_dir, tmp_path
):
    with pytest.raises(SystemExit):
        main(
            ground_argv(
                project,
                openenv_server,
                prepared_dir,
                tmp_path / "run",
                "--provider",
                "p",
            ),
            claude_runner=FakeClaude([]),
        )


def test_ground_reports_a_missing_server(project, prepared_dir, tmp_path, capsys):
    argv = [
        "ground",
        "--project",
        str(project.path),
        "--openenv-server-id",
        "nope",
        "--in",
        str(prepared_dir),
        "--out",
        str(tmp_path / "run"),
        "--engine",
        "claude",
    ]
    assert main(argv, claude_runner=FakeClaude([])) == 1
    assert "no OpenEnv server with id nope" in capsys.readouterr().err


def test_summarize_sums_usage_across_cases():
    def dropped(cost: float | None) -> CaseRun:
        from kiln_ai.eval_grounding.models import GroundingOutcome

        return CaseRun(
            case_index=0,
            outcome=GroundingOutcome.dropped(
                DropReason.no_fit,
                "x",
                call_log=[],
                usage=Usage(input_tokens=1, cost=cost) if cost is not None else None,
            ),
            error=None,
        )

    summary = summarize(
        [dropped(0.5), dropped(0.25), dropped(None)],
        engine="claude",
        model="m",
        case_count=3,
    )
    assert summary["usage"] == {"input_tokens": 2, "cost": 0.75}
    assert summary["drops_by_reason"] == {"no_fit": 3}


# ---- run_claude ----


def fake_claude_script(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake_claude.py"
    script.write_text(f"#!{sys.executable}\nimport json, sys, time\n{body}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


async def test_run_claude_reads_the_json_result(tmp_path):
    script = fake_claude_script(
        tmp_path,
        "prompt = sys.stdin.read()\n"
        "print(json.dumps({'type': 'result', 'is_error': False, 'result': prompt.upper(),"
        " 'session_id': 's1', 'total_cost_usd': 0.1,"
        " 'usage': {'input_tokens': 5, 'cache_read_input_tokens': 20,"
        " 'cache_creation_input_tokens': 3, 'output_tokens': 7}}))",
    )
    result = await run_claude(
        [str(script), "-p"], stdin="hello", cwd=tmp_path, timeout_s=30
    )
    assert result.result == "HELLO"
    assert result.session_id == "s1"
    assert result.usage.input_tokens == 28
    assert result.usage.cached_tokens == 20
    assert result.usage.output_tokens == 7
    assert result.usage.total_tokens == 35
    assert result.usage.cost == 0.1


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("sys.stderr.write('not logged in'); sys.exit(1)", "not logged in"),
        (
            "print(json.dumps({'is_error': True, 'subtype': 'error_max_turns', 'result': 'x'}))",
            "error_max_turns",
        ),
        ("print('plain text')", "not JSON"),
    ],
)
async def test_run_claude_raises_on_failure(tmp_path, body, message):
    script = fake_claude_script(tmp_path, body)
    with pytest.raises(ClaudeRunError, match=message):
        await run_claude([str(script)], stdin="", cwd=tmp_path, timeout_s=30)


async def test_run_claude_kills_a_run_past_its_time(tmp_path):
    marker = tmp_path / "finished"
    script = fake_claude_script(
        tmp_path, f"time.sleep(30)\nopen({str(marker)!r}, 'w').close()"
    )
    with pytest.raises(TimeoutError):
        await run_claude([str(script)], stdin="", cwd=tmp_path, timeout_s=0.5)
    assert not marker.exists()


async def test_run_claude_kills_a_cancelled_run(tmp_path):
    pid_file = tmp_path / "pid"
    marker = tmp_path / "finished"
    script = fake_claude_script(
        tmp_path,
        f"import os\nopen({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        f"time.sleep(30)\nopen({str(marker)!r}, 'w').close()",
    )
    run = asyncio.create_task(
        run_claude([str(script)], stdin="", cwd=tmp_path, timeout_s=60)
    )
    for _ in range(200):
        if pid_file.exists() and pid_file.read_text():
            break
        await asyncio.sleep(0.05)
    pid = int(pid_file.read_text())
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert not marker.exists()


def test_a_stale_run_log_from_an_earlier_run_is_not_read(
    project, openenv_server, prepared_dir, tmp_path
):
    out = tmp_path / "run"
    (out / "case_000").mkdir(parents=True)
    (out / "case_000" / "run_log.json").write_text(run_log().model_dump_json())
    (out / "case_000" / "claude_retry_output.json").write_text("{}")

    async def runner(argv, *, stdin, cwd, timeout_s):
        return reply(GROUNDED_REPLY)

    code = main(
        ground_argv(project, openenv_server, prepared_dir, out), claude_runner=runner
    )
    assert code == 1
    [failed] = read_json(out / "summary.json")["failed_cases"]
    assert "never started" in failed["error"]
    assert not (out / "case_000" / "claude_retry_output.json").exists()


def test_a_retry_that_claude_rejects_is_an_invalid_output_drop(
    project, openenv_server, prepared_dir, tmp_path
):
    out = tmp_path / "run"
    fake = FakeClaude([reply("oops"), ClaudeRunError("tools are not defined")])
    code = main(
        ground_argv(project, openenv_server, prepared_dir, out), claude_runner=fake
    )
    assert code == 0
    [outcome] = read_json(out / "outcomes.json")
    assert outcome["outcome"]["drop_reason"] == "invalid_output"
    assert outcome["outcome"]["usage"]["cost"] == 0.5
    assert outcome["outcome"]["usage_complete"] is False


def test_a_timeout_after_an_environment_error_fails_the_case(
    project, openenv_server, prepared_dir, tmp_path
):
    out = tmp_path / "run"
    fake = FakeClaude(
        [TimeoutError()], log=run_log(stopped="error", stop_detail="server gone")
    )
    code = main(
        ground_argv(project, openenv_server, prepared_dir, out), claude_runner=fake
    )
    assert code == 1
    [failed] = read_json(out / "summary.json")["failed_cases"]
    assert "server gone" in failed["error"]


def test_claude_md_files_above(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("notes")
    inner = tmp_path / "a" / "b"
    inner.mkdir(parents=True)
    assert tmp_path.resolve() / "CLAUDE.md" in claude_md_files_above(inner)


@pytest.mark.parametrize(("bare", "warned"), [(False, True), (True, False)])
def test_ground_warns_about_claude_md_above_the_run_folder(
    project, openenv_server, prepared_dir, tmp_path, capsys, bare, warned
):
    (tmp_path / "CLAUDE.md").write_text("notes")
    extra = ["--claude-bare"] if bare else []
    main(
        ground_argv(project, openenv_server, prepared_dir, tmp_path / "run", *extra),
        claude_runner=FakeClaude([reply(GROUNDED_REPLY)]),
    )
    assert ("Warning: claude will load" in capsys.readouterr().err) == warned
