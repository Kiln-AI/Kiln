"""Developer command for grounding Eval Builder cases in an OpenEnv server.

Two stages, so the paid planning step runs once and grounding can be rerun while the
grounding prompt changes:

    uv run python -m app.desktop.studio_server.dev.ground_cases prepare \\
        --project <project.kiln> --task-id <id> --openenv-server-id <id> \\
        --spec <file> --base-guidance <file> [--data-guide <file>] --count <n> --out <dir>

    uv run python -m app.desktop.studio_server.dev.ground_cases ground \\
        --project <project.kiln> --openenv-server-id <id> --in <prepare's dir> \\
        --out <run dir> --engine claude [--model <name>] [--prompt <file>] [--cases 0,3-5]

`prepare` reads the server's reset schema and metadata, builds the planner guidance, and calls
kiln_server's batch planner and simulated-user generation. It needs the Kiln Copilot API key in
Kiln's settings. `--base-guidance` is the multi-turn plan guidance the web UI sends for the
spec, saved to a file.

`ground --engine claude` runs `claude -p` once per case, with the grounding tools served by
`grounding_mcp.py`. Each case's files (MCP config, message, raw `claude` output, run log) are
kept in `<run dir>/case_<n>/`.

`ground --engine kiln --model <name> --provider <provider>` runs the grounding agent on a Kiln
model through `ground_cases`, the way the product will, with the user's own API keys from
Kiln's settings. `--answer-style` picks how the agent hands back its result: a JSON response
format (`structured_output`, the default) or a `submit_result` tool.

Both engines write `system_prompt.txt`, `outcomes.json` (every outcome with its call log) and
`summary.json` to the run folder.

`claude` runs in the case folder. Without `--claude-bare` it still loads the user's own
CLAUDE.md and memory, and any CLAUDE.md in the case folder's parents, into the grounding
agent's context, so put `--out` outside any repository. `--claude-bare` keeps all of that
out, but it authenticates only with ANTHROPIC_API_KEY, not a Claude subscription.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import re
import sys
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException
from kiln_ai.adapters.retry_classification import unwrap_kiln_run_error
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.openenv import OpenEnvServer, OpenEnvTool
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.task import Task
from kiln_ai.eval_grounding.agent import time_limit_detail
from kiln_ai.eval_grounding.batch import (
    CaseGrounded,
    GroundingCaseError,
    ground_cases,
)
from kiln_ai.eval_grounding.models import (
    DropReason,
    EvalContext,
    GroundingCase,
    GroundingOutcome,
    GroundingResult,
)
from kiln_ai.eval_grounding.prompt import (
    KilnAnswerStyle,
    case_message,
    follow_up_message,
    system_prompt,
)
from kiln_ai.eval_grounding.session import DEFAULT_TIME_LIMIT_S
from kiln_ai.openenv.reset_schema_brief import reset_arguments_brief
from kiln_ai.openenv.session_manager import OpenEnvError, OpenEnvSessionManager
from kiln_ai.synthetic_user.runner import CONCURRENCY
from kiln_ai.tools.base_tool import ToolCallDefinition, ToolFunction
from kiln_ai.tools.mcp_session_manager import mcp_session_scope
from kiln_ai.tools.run_config_tools import tool_definitions_without_episode
from kiln_ai.utils.usage import Usage
from pydantic import JsonValue, ValidationError

from app.desktop.studio_server.batch_plan_api import _run_batch_plan_kiln_server
from app.desktop.studio_server.data_gen_api import _resolve_task_runtime_prompt
from app.desktop.studio_server.dev import grounding_mcp
from app.desktop.studio_server.dev.grounding_mcp import (
    MCP_SERVER_NAME,
    GroundingRunLog,
    GroundingSetupError,
    load_openenv_server,
)
from app.desktop.studio_server.multiturn_sdg_api import (
    _case_chunks,
    _case_dict_at_plan_offset,
)
from app.desktop.studio_server.synthetic_user.client import (
    SyntheticUserClient,
    SyntheticUserError,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key

DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"

DATA_GUIDE_FRAMING = """## Data Guide

The user wrote the guide below about who talks to this agent and what they ask. Take the people in your scenarios, and the kinds of requests they make, from it. Where it says how common something is, follow that in the batch. Where it is silent, use your judgment as usual. It describes users, not test goals: the specification above still decides what each scenario stresses."""
"""The planner's framing for the Data Guide text, which follows it in `<data_guide>` tags."""

PREPARED_FILES = (
    "specification.txt",
    "task_prompt.txt",
    "schema.json",
    "metadata.json",
    "brief.txt",
    "guidance.txt",
    "plan.json",
    "users.json",
)
"""What `prepare` always writes to its output folder."""

DATA_GUIDE_FILE = "data_guide.txt"
"""Written by `prepare` only when it was given a Data Guide."""


class CaseFailedError(Exception):
    """A case could not be grounded for a reason that is not the case's fault."""


class ClaudeRunError(CaseFailedError):
    """`claude` exited with an error, or printed something that is not its JSON result."""


# ---- prepare ----


def compose_guidance(
    base_guidance: str, brief: str | None, data_guide: str | None
) -> str:
    """The planner's guidance: the base multi-turn guidance, then the reset-arguments
    brief, then the Data Guide section. Empty parts are left out."""
    sections = [base_guidance.strip()]
    if brief:
        sections.append(brief.strip())
    if data_guide and data_guide.strip():
        sections.append(
            f"{DATA_GUIDE_FRAMING}\n\n<data_guide>\n{data_guide.strip()}\n</data_guide>"
        )
    return "\n\n".join(s for s in sections if s)


@dataclass(frozen=True)
class PrepareArgs:
    project: Path
    task_id: str
    openenv_server_id: str
    spec: Path
    base_guidance: Path
    data_guide: Path | None
    count: int
    out: Path


async def prepare(args: PrepareArgs, *, copilot_api_key: str) -> None:
    """Write every input a grounding run reuses to `args.out`."""
    task = _load_task(args.project, args.task_id)
    openenv_server = load_openenv_server(args.project, args.openenv_server_id)
    spec_text = await _read_text(args.spec)
    base_guidance = await _read_text(args.base_guidance)
    data_guide = await _read_text(args.data_guide) if args.data_guide else None
    await asyncio.to_thread(args.out.mkdir, parents=True, exist_ok=True)
    # A rerun that fails part way must leave a folder load_prepared refuses, not this
    # run's inputs beside an earlier run's plan and users.
    for name in (*PREPARED_FILES, DATA_GUIDE_FILE):
        await asyncio.to_thread((args.out / name).unlink, missing_ok=True)
    await _write_text(args.out / "specification.txt", spec_text)
    await _write_text(args.out / "task_prompt.txt", task.instruction)
    if data_guide and data_guide.strip():
        await _write_text(args.out / DATA_GUIDE_FILE, data_guide)

    session_manager = OpenEnvSessionManager()
    try:
        reset_schema = await session_manager.reset_schema(openenv_server)
        metadata = await session_manager.metadata(openenv_server)
    finally:
        await session_manager.shutdown()
    brief = reset_arguments_brief(reset_schema)
    await _write_json(args.out / "schema.json", reset_schema)
    await _write_json(args.out / "metadata.json", dataclasses.asdict(metadata))
    await _write_text(args.out / "brief.txt", brief or "")
    _progress(
        "Reset arguments brief written."
        if brief
        else "The server publishes no reset arguments; the guidance has no brief."
    )

    guidance = compose_guidance(base_guidance, brief, data_guide)
    await _write_text(args.out / "guidance.txt", guidance)
    _progress(f"Planning {args.count} cases with kiln_server's batch planner...")
    plan = await _run_batch_plan_kiln_server(
        task_prompt=_resolve_task_runtime_prompt(task),
        task_input_schema=task.input_json_schema,
        task_output_schema=task.output_json_schema,
        input_data_guide=None,
        user_guidance=guidance,
        count=args.count,
    )
    await _write_json(args.out / "plan.json", plan.model_dump())

    _progress(f"Writing simulated users for {len(plan.prompts)} planned cases...")
    users = await _generate_users(
        SyntheticUserClient(api_key=copilot_api_key),
        target_task_prompt=task.instruction,
        target_specification=spec_text,
        scenarios=plan.prompts,
    )
    await _write_json(args.out / "users.json", users)
    _progress(f"Prepared {len(users)} cases in {args.out}.")


async def _generate_users(
    client: SyntheticUserClient,
    *,
    target_task_prompt: str,
    target_specification: str,
    scenarios: list[str],
) -> list[dict[str, Any]]:
    """One simulated user per scenario, from kiln_server one chunk at a time, with
    `scenario_index` counted from the start of the plan."""
    users: list[dict[str, Any]] = []
    for start, chunk_scenarios in _case_chunks(scenarios):
        chunk = await client.generate(
            target_task_prompt=target_task_prompt,
            target_specification=target_specification,
            case_scenarios=chunk_scenarios,
        )
        users.extend(_case_dict_at_plan_offset(case, start) for case in chunk)
    return users


def _load_task(project_path: Path, task_id: str) -> Task:
    if not project_path.is_file():
        raise GroundingSetupError(f"No project file at {project_path}.")
    project = Project.load_from_file(project_path)
    task = next((t for t in project.tasks(readonly=True) if t.id == task_id), None)
    if task is None:
        raise GroundingSetupError(
            f"Project {project.name} has no task with id {task_id}."
        )
    return task


# ---- ground ----


@dataclass(frozen=True)
class PreparedInputs:
    """What `prepare` wrote, as `ground` reads it."""

    cases: list[GroundingCase]
    eval_context: EvalContext
    reset_schema: dict[str, JsonValue] | None


def load_prepared(in_dir: Path) -> PreparedInputs:
    """`prepare`'s output, with each simulated user joined to its plan prompt."""
    missing = [name for name in PREPARED_FILES if not (in_dir / name).is_file()]
    if missing:
        raise GroundingSetupError(
            f"{in_dir} is not a complete prepare folder: missing {', '.join(missing)}. "
            "Run prepare again, or write the missing files into the folder."
        )
    plan = json.loads((in_dir / "plan.json").read_text(encoding="utf-8"))
    users = json.loads((in_dir / "users.json").read_text(encoding="utf-8"))
    prompts: list[str] = plan["prompts"]
    cases = [
        GroundingCase(
            scenario=prompts[user["scenario_index"]],
            seed_prompt=user["seed_prompt"],
            synthetic_user_info=user["synthetic_user_info"],
        )
        for user in users
    ]
    data_guide_path = in_dir / DATA_GUIDE_FILE
    data_guide = (
        data_guide_path.read_text(encoding="utf-8") if data_guide_path.is_file() else ""
    )
    return PreparedInputs(
        cases=cases,
        eval_context=EvalContext(
            specification=(in_dir / "specification.txt").read_text(encoding="utf-8"),
            target_task_prompt=(in_dir / "task_prompt.txt").read_text(encoding="utf-8"),
            data_guide=data_guide if data_guide.strip() else None,
        ),
        reset_schema=json.loads((in_dir / "schema.json").read_text(encoding="utf-8")),
    )


def parse_case_indices(raw: str | None, case_count: int) -> list[int]:
    """`--cases`: comma-separated indices and inclusive ranges (`0,3-5`); all cases when
    absent."""
    if raw is None:
        return list(range(case_count))
    indices: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if match is None:
            raise GroundingSetupError(f"--cases: '{part}' is not an index or a range.")
        first = int(match.group(1))
        last = int(match.group(2) or first)
        indices.update(range(first, last + 1))
    out_of_range = sorted(i for i in indices if i >= case_count)
    if out_of_range:
        raise GroundingSetupError(
            f"--cases: {out_of_range} out of range; the prepare folder has {case_count} cases."
        )
    return sorted(indices)


def parse_grounding_result(text: str) -> GroundingResult:
    """The JSON object in the agent's final reply. Code fences and prose around the object
    are tolerated. Raises ValueError (including pydantic's ValidationError) when there is
    no usable object."""
    try:
        return GroundingResult.model_validate_json(text.strip())
    except ValidationError as e:
        if not _is_json_error(e):
            raise
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("The reply has no JSON object.")
    return GroundingResult.model_validate_json(text[start : end + 1])


def without_mcp_tool_prefix(result: GroundingResult) -> GroundingResult:
    """The result with each fact's tool named as the environment names it. claude sees
    the grounding server's tools as `mcp__<server>__<tool>` and sometimes cites them that
    way; the judge only knows the environment's own tool names."""
    if result.reference is None:
        return result
    prefix = f"mcp__{MCP_SERVER_NAME}__"
    facts = [
        fact.model_copy(
            update={
                "evidence": fact.evidence.model_copy(
                    update={"tool": fact.evidence.tool.removeprefix(prefix)}
                )
            }
        )
        for fact in result.reference.facts
    ]
    return result.model_copy(
        update={"reference": result.reference.model_copy(update={"facts": facts})}
    )


def _is_json_error(error: ValidationError) -> bool:
    return any(e["type"] == "json_invalid" for e in error.errors())


def target_tool_definitions(tools: list[OpenEnvTool]) -> list[ToolCallDefinition]:
    """The server's tools, as the agent under test would see them."""
    return [
        ToolCallDefinition(
            type="function",
            function=ToolFunction(
                name=tool.name,
                description=tool.description,
                parameters=tool.input_schema,
            ),
        )
        for tool in tools
    ]


@dataclass(frozen=True)
class ClaudeReply:
    """`claude -p --output-format json`'s result, and its raw output."""

    result: str
    session_id: str | None
    usage: Usage
    raw: str


ClaudeRunner = Callable[..., Awaitable[ClaudeReply]]
"""Runs `claude` with `(argv, *, stdin, cwd, timeout_s)`; `run_claude` is the real one."""


async def run_claude(
    argv: Sequence[str], *, stdin: str, cwd: Path, timeout_s: float
) -> ClaudeReply:
    """Run `claude` and read its JSON result. Raises TimeoutError when it runs past
    `timeout_s`, and ClaudeRunError when it fails. `claude` is killed if it is still
    running when this returns or is cancelled."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(stdin.encode("utf-8")), timeout=timeout_s
        )
    finally:
        # A timeout or a cancelled run would otherwise leave claude (and the MCP server
        # it started) running and spending.
        if process.returncode is None:
            process.kill()
            await process.wait()
    raw = stdout.decode("utf-8", errors="replace")
    if process.returncode != 0:
        raise ClaudeRunError(
            f"claude exited with code {process.returncode}: "
            f"{stderr.decode('utf-8', errors='replace').strip() or raw.strip()}"
        )
    return parse_claude_output(raw)


def parse_claude_output(raw: str) -> ClaudeReply:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ClaudeRunError(f"claude printed output that is not JSON: {e}") from e
    if not isinstance(data, dict):
        raise ClaudeRunError("claude printed JSON that is not an object.")
    if data.get("is_error"):
        raise ClaudeRunError(
            f"claude reported an error ({data.get('subtype')}): {data.get('result')}"
        )
    return ClaudeReply(
        result=str(data.get("result") or ""),
        session_id=data.get("session_id"),
        usage=_claude_usage(data),
        raw=raw,
    )


def _claude_usage(data: dict[str, Any]) -> Usage:
    usage = data.get("usage") or {}
    cached = usage.get("cache_read_input_tokens") or 0
    # Claude reports cache reads and writes apart from the uncached input tokens.
    input_tokens = (
        (usage.get("input_tokens") or 0)
        + cached
        + (usage.get("cache_creation_input_tokens") or 0)
    )
    output_tokens = usage.get("output_tokens") or 0
    cost = data.get("total_cost_usd")
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cached_tokens=cached,
        cost=float(cost) if isinstance(cost, (int, float)) else None,
    )


@dataclass(frozen=True)
class ClaudeEngine:
    """Grounds one case per `claude -p` run, each with its own grounding MCP server."""

    claude_bin: str
    model: str
    system_prompt: str
    project_path: Path
    openenv_server_id: str
    bare: bool = False
    effort: str | None = None
    time_limit_s: float = DEFAULT_TIME_LIMIT_S
    runner: ClaudeRunner = run_claude

    def mcp_config(self, log_path: Path) -> dict[str, Any]:
        return {
            "mcpServers": {
                MCP_SERVER_NAME: {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [
                        str(grounding_mcp.script_path()),
                        "--project",
                        str(self.project_path.resolve()),
                        "--openenv-server-id",
                        self.openenv_server_id,
                        "--log-out",
                        str(log_path.resolve()),
                    ],
                }
            }
        }

    def argv(self, mcp_config_path: Path) -> list[str]:
        """The first run: only the grounding server's tools, no built-in tools."""
        return [
            *self._common_argv(),
            "--mcp-config",
            str(mcp_config_path.resolve()),
            "--strict-mcp-config",
            "--allowedTools",
            f"mcp__{MCP_SERVER_NAME}__*",
        ]

    def retry_argv(self, session_id: str) -> list[str]:
        """The follow-up after an unusable reply: the same session with no tools at all.
        Without the case's MCP server the agent can't start another episode, and no new
        server overwrites the case's run log."""
        return [*self._common_argv(), "--resume", session_id, "--strict-mcp-config"]

    def _common_argv(self) -> list[str]:
        argv = [
            self.claude_bin,
            "-p",
            "--model",
            self.model,
            "--output-format",
            "json",
            "--tools",
            "",
            "--permission-mode",
            "dontAsk",
            "--system-prompt",
            self.system_prompt,
        ]
        if self.effort is not None:
            argv += ["--effort", self.effort]
        if self.bare:
            argv.append("--bare")
        return argv

    async def ground_case(self, message: str, case_dir: Path) -> GroundingOutcome:
        log_path = case_dir / "run_log.json"
        await asyncio.to_thread(case_dir.mkdir, parents=True, exist_ok=True)
        # A rerun into the same --out must not read the last run's log or retry output.
        for stale in (log_path, case_dir / "claude_retry_output.json"):
            await asyncio.to_thread(stale.unlink, missing_ok=True)
        mcp_config_path = case_dir / "mcp_config.json"
        await _write_json(mcp_config_path, self.mcp_config(log_path))
        await _write_text(case_dir / "message.txt", message)
        deadline = asyncio.get_running_loop().time() + self.time_limit_s

        try:
            reply = await self._run(
                self.argv(mcp_config_path), message, case_dir, deadline
            )
        except TimeoutError:
            run_log = await _read_run_log(log_path)
            _raise_if_session_failed(run_log)
            return GroundingOutcome.dropped(
                DropReason.limit,
                time_limit_detail(self.time_limit_s),
                call_log=run_log.call_log,
                usage=None,
                usage_complete=False,
            )
        await _write_text(case_dir / "claude_output.json", reply.raw)

        run_log = await _read_run_log(log_path)
        _raise_if_session_failed(run_log)
        if run_log.stopped == "limit":
            return GroundingOutcome.dropped(
                DropReason.limit,
                run_log.stop_detail or "The agent ran out of tool calls or resets.",
                call_log=run_log.call_log,
                usage=reply.usage,
            )

        result, parse_error, usage, usage_complete = await self._result_with_one_retry(
            reply, case_dir, deadline
        )
        if result is None:
            return GroundingOutcome.dropped(
                DropReason.invalid_output,
                f"The agent's reply was not a usable result: {parse_error}",
                call_log=run_log.call_log,
                usage=usage,
                usage_complete=usage_complete,
            )
        return GroundingOutcome.from_result(
            without_mcp_tool_prefix(result),
            openenv_reset=run_log.last_reset,
            call_log=run_log.call_log,
            usage=usage,
            usage_complete=usage_complete,
        )

    async def _result_with_one_retry(
        self, reply: ClaudeReply, case_dir: Path, deadline: float
    ) -> tuple[GroundingResult | None, str | None, Usage, bool]:
        """The reply's result, or, when it doesn't parse, the result of one follow-up in
        the same session. Returns the first parse error when neither parses, the usage
        of every call made, and whether that usage is complete: a follow-up that timed
        out or failed reports none."""
        try:
            return parse_grounding_result(reply.result), None, reply.usage, True
        except ValueError as e:
            parse_error = _first_line(e)
        if reply.session_id is None:
            return None, parse_error, reply.usage, True
        try:
            retry = await self._run(
                self.retry_argv(reply.session_id),
                follow_up_message(parse_error, "reply_json"),
                case_dir,
                deadline,
            )
        except (TimeoutError, ClaudeRunError):
            return None, parse_error, reply.usage, False
        await _write_text(case_dir / "claude_retry_output.json", retry.raw)
        usage = reply.usage + retry.usage
        try:
            return parse_grounding_result(retry.result), None, usage, True
        except ValueError:
            return None, parse_error, usage, True

    async def _run(
        self, argv: list[str], stdin: str, cwd: Path, deadline: float
    ) -> ClaudeReply:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError
        return await self.runner(argv, stdin=stdin, cwd=cwd, timeout_s=remaining)


@dataclass(frozen=True)
class GroundArgs:
    project: Path
    openenv_server_id: str
    in_dir: Path
    out: Path
    engine: Literal["claude", "kiln"]
    model: str | None
    provider: ModelProviderName | None
    answer_style: KilnAnswerStyle
    prompt: Path | None
    cases: str | None
    claude_bin: str
    claude_bare: bool
    thinking_level: str | None = None
    task_id: str | None = None
    run_config_id: str | None = None


@dataclass(frozen=True)
class CaseRun:
    case_index: int
    outcome: GroundingOutcome | None
    error: str | None


async def ground(args: GroundArgs, *, claude_runner: ClaudeRunner = run_claude) -> int:
    """Ground the prepared cases; returns the process exit code."""
    openenv_server = load_openenv_server(args.project, args.openenv_server_id)
    prepared = await asyncio.to_thread(load_prepared, args.in_dir)
    indices = parse_case_indices(args.cases, len(prepared.cases))
    target_tools = (
        await _run_config_target_tools(args.project, args.task_id, args.run_config_id)
        if args.run_config_id is not None
        else target_tool_definitions(await _list_server_tools(openenv_server))
    )
    prompt_text = (
        await _read_text(args.prompt)
        if args.prompt is not None
        else system_prompt(
            answer_style="reply_json" if args.engine == "claude" else args.answer_style
        )
    )
    await asyncio.to_thread(args.out.mkdir, parents=True, exist_ok=True)
    await _write_text(args.out / "system_prompt.txt", prompt_text)

    if args.engine == "kiln":
        if args.model is None or args.provider is None:
            raise GroundingSetupError("--engine kiln needs --model and --provider.")
        model = args.model
        runs, batch_error = await _ground_with_kiln(
            args,
            prepared,
            indices,
            model=model,
            provider=args.provider,
            openenv_server=openenv_server,
            target_tools=target_tools,
            prompt_text=prompt_text,
        )
    else:
        model = args.model or DEFAULT_CLAUDE_MODEL
        runs = await _ground_with_claude(
            args,
            prepared,
            indices,
            target_tools=target_tools,
            prompt_text=prompt_text,
            model=model,
            claude_runner=claude_runner,
        )
        batch_error = None

    runs = sorted(runs, key=lambda run: run.case_index)
    await _write_json(
        args.out / "outcomes.json",
        [
            {
                "case_index": run.case_index,
                "outcome": run.outcome.model_dump(mode="json"),
            }
            for run in runs
            if run.outcome is not None
        ],
    )
    summary = summarize(runs, engine=args.engine, model=model, case_count=len(indices))
    if args.engine == "kiln":
        summary["provider"] = args.provider
        summary["answer_style"] = args.answer_style
        summary["error"] = batch_error
    await _write_json(args.out / "summary.json", summary)
    _progress(
        f"{summary['grounded']} grounded, {summary['dropped']} dropped, "
        f"{len(summary['failed_cases'])} failed. Results in {args.out}."
    )
    return 1 if summary["failed_cases"] or batch_error else 0


async def _ground_with_claude(
    args: GroundArgs,
    prepared: PreparedInputs,
    indices: list[int],
    *,
    target_tools: list[ToolCallDefinition],
    prompt_text: str,
    model: str,
    claude_runner: ClaudeRunner,
) -> list[CaseRun]:
    engine = ClaudeEngine(
        claude_bin=args.claude_bin,
        model=model,
        system_prompt=prompt_text,
        project_path=args.project,
        openenv_server_id=args.openenv_server_id,
        bare=args.claude_bare,
        effort=args.thinking_level,
        runner=claude_runner,
    )
    if not args.claude_bare:
        claude_mds = await asyncio.to_thread(claude_md_files_above, args.out)
        if claude_mds:
            _progress(
                "Warning: claude will load these into the grounding agent's context: "
                f"{', '.join(str(p) for p in claude_mds)}. Put --out outside any "
                "repository, or use --claude-bare."
            )

    slots = asyncio.Semaphore(CONCURRENCY)
    finished = 0

    async def run_case(case_index: int) -> CaseRun:
        nonlocal finished
        message = case_message(
            prepared.cases[case_index],
            eval_context=prepared.eval_context,
            reset_schema=prepared.reset_schema,
            target_tools=target_tools,
        )
        async with slots:
            try:
                outcome = await engine.ground_case(
                    message, args.out / f"case_{case_index:03d}"
                )
                run = CaseRun(case_index, outcome, None)
            except CaseFailedError as e:
                run = CaseRun(case_index, None, str(e))
        finished += 1
        _progress(
            f"[{finished}/{len(indices)}] case {case_index}: {_describe_run(run)}"
        )
        return run

    return list(await asyncio.gather(*(run_case(i) for i in indices)))


async def _ground_with_kiln(
    args: GroundArgs,
    prepared: PreparedInputs,
    indices: list[int],
    *,
    model: str,
    provider: ModelProviderName,
    openenv_server: OpenEnvServer,
    target_tools: list[ToolCallDefinition],
    prompt_text: str,
) -> tuple[list[CaseRun], str | None]:
    """The grounded cases, and the error that stopped the batch, if one did. Like the
    product, one case's error stops every case, so the cases after it have no run."""
    runs: list[CaseRun] = []
    session_manager = OpenEnvSessionManager()
    try:
        async for event in ground_cases(
            [prepared.cases[i] for i in indices],
            eval_context=prepared.eval_context,
            openenv_server=openenv_server,
            session_manager=session_manager,
            model_name=model,
            model_provider=provider,
            target_tools=target_tools,
            thinking_level=args.thinking_level,
            answer_style=args.answer_style,
            system_prompt_text=prompt_text,
        ):
            if isinstance(event, CaseGrounded):
                run = CaseRun(indices[event.case_index], event.outcome, None)
                runs.append(run)
                _progress(
                    f"[{len(runs)}/{len(indices)}] case {run.case_index}: "
                    f"{_describe_run(run)}"
                )
    except Exception as e:
        error = _describe_batch_error(e, indices)
        _progress(f"Grounding stopped: {error}")
        return runs, error
    finally:
        await session_manager.shutdown()
    return runs, None


def _describe_batch_error(error: Exception, indices: list[int]) -> str:
    """The error that stopped a kiln batch, with the case that raised it and the
    underlying error's type, which KilnRunError's own message hides."""
    case = ""
    if isinstance(error, GroundingCaseError):
        case = f"case {indices[error.case_index]}: "
        error = error.error
    cause = unwrap_kiln_run_error(error)
    return f"{case}{type(cause).__name__}: {cause}"


def summarize(
    runs: Sequence[CaseRun], *, engine: str, model: str, case_count: int
) -> dict[str, Any]:
    """The run's counts, each grounded case's reset arguments, and its token use.
    `case_count` is the cases asked for, which a stopped batch has fewer runs for."""
    outcomes = [(run.case_index, run.outcome) for run in runs if run.outcome]
    grounded = [(i, o) for i, o in outcomes if o.status == "grounded"]
    drops = Counter(
        o.drop_reason.value for _, o in outcomes if o.drop_reason is not None
    )
    usage = Usage()
    for _, outcome in outcomes:
        if outcome.usage is not None:
            usage = usage + outcome.usage
    return {
        "engine": engine,
        "model": model,
        "cases": case_count,
        "grounded": len(grounded),
        "dropped": len(outcomes) - len(grounded),
        "drops_by_reason": dict(sorted(drops.items())),
        "failed_cases": [
            {"case_index": run.case_index, "error": run.error}
            for run in runs
            if run.error is not None
        ],
        "grounded_resets": [
            {
                "case_index": i,
                "reset_kwargs": o.openenv_reset.reset_kwargs
                if o.openenv_reset
                else None,
            }
            for i, o in grounded
        ],
        "usage": usage.model_dump(mode="json", exclude_none=True),
        # Usage misses some model calls on these cases, so it is not a full total.
        "cases_with_incomplete_usage": sum(
            1 for _, o in outcomes if not o.usage_complete
        ),
    }


def _describe_run(run: CaseRun) -> str:
    if run.outcome is None:
        return f"failed: {run.error}"
    if run.outcome.status == "grounded":
        return "grounded"
    reason = run.outcome.drop_reason.value if run.outcome.drop_reason else "?"
    return f"dropped ({reason}): {run.outcome.drop_detail}"


async def _run_config_target_tools(
    project_path: Path, task_id: str | None, run_config_id: str
) -> list[ToolCallDefinition]:
    """The agent-under-test tool list the product's grounding step reads: the tools on
    the task's run config."""
    if task_id is None:
        raise GroundingSetupError("--run-config-id needs --task-id.")
    task = await asyncio.to_thread(_load_task, project_path, task_id)
    run_config = next(
        (rc for rc in task.run_configs(readonly=True) if rc.id == run_config_id), None
    )
    if run_config is None:
        raise GroundingSetupError(
            f"Task {task.name} has no run config with id {run_config_id}."
        )
    properties = run_config.run_config_properties
    tools_config = getattr(properties, "tools_config", None)
    tool_ids = list(tools_config.tools) if tools_config is not None else []
    session_manager = OpenEnvSessionManager()
    try:
        async with mcp_session_scope():
            return await tool_definitions_without_episode(
                task, tool_ids, session_manager
            )
    finally:
        await session_manager.shutdown()


async def _list_server_tools(openenv_server: OpenEnvServer) -> list[OpenEnvTool]:
    session_manager = OpenEnvSessionManager()
    try:
        return await session_manager.list_tools(openenv_server)
    finally:
        await session_manager.shutdown()


async def _read_run_log(log_path: Path) -> GroundingRunLog:
    """The grounding MCP server's log. It writes one as soon as it starts, so a missing
    log means `claude` never started it."""
    try:
        text = await asyncio.to_thread(log_path.read_text, encoding="utf-8")
    except FileNotFoundError as e:
        raise CaseFailedError(
            f"The grounding MCP server never started: no run log at {log_path}. "
            "Check claude_output.json in the case folder."
        ) from e
    try:
        return GroundingRunLog.model_validate_json(text)
    except ValidationError as e:
        raise CaseFailedError(f"The run log at {log_path} is not valid: {e}") from e


def claude_md_files_above(folder: Path) -> list[Path]:
    """The CLAUDE.md files `claude` would find from `folder` up to the filesystem root."""
    folder = folder.resolve()
    return [
        directory / "CLAUDE.md"
        for directory in (folder, *folder.parents)
        if (directory / "CLAUDE.md").is_file()
    ]


def _raise_if_session_failed(run_log: GroundingRunLog) -> None:
    if run_log.stopped == "error":
        raise CaseFailedError(f"The grounding session stopped: {run_log.stop_detail}")


def _first_line(error: Exception) -> str:
    return str(error).strip().splitlines()[0] if str(error).strip() else repr(error)


# ---- files and output ----


async def _read_text(path: Path) -> str:
    return await asyncio.to_thread(path.read_text, encoding="utf-8")


async def _write_text(path: Path, text: str) -> None:
    await asyncio.to_thread(path.write_text, text, encoding="utf-8")


async def _write_json(path: Path, data: Any) -> None:
    await _write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


# ---- command line ----


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ground Eval Builder cases in an OpenEnv server (developer prototype)."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prep = commands.add_parser(
        "prepare", help="Plan the cases and draft their simulated users."
    )
    prep.add_argument("--project", type=Path, required=True)
    prep.add_argument("--task-id", required=True)
    prep.add_argument("--openenv-server-id", required=True)
    prep.add_argument(
        "--spec", type=Path, required=True, help="The eval's specification text."
    )
    prep.add_argument(
        "--base-guidance",
        type=Path,
        required=True,
        help="The multi-turn plan guidance the web UI sends for this spec.",
    )
    prep.add_argument(
        "--data-guide",
        type=Path,
        help="Who uses the agent and what they ask, for the planner.",
    )
    prep.add_argument("--count", type=int, required=True)
    prep.add_argument("--out", type=Path, required=True)

    grd = commands.add_parser("ground", help="Ground prepared cases.")
    grd.add_argument("--project", type=Path, required=True)
    grd.add_argument("--openenv-server-id", required=True)
    grd.add_argument("--in", dest="in_dir", type=Path, required=True)
    grd.add_argument(
        "--out",
        type=Path,
        required=True,
        help="The run folder. claude runs in its case folders, so keep it outside any "
        "repository: claude loads CLAUDE.md files from the folders above.",
    )
    grd.add_argument("--engine", choices=["claude", "kiln"], required=True)
    grd.add_argument(
        "--model", help=f"Default for --engine claude: {DEFAULT_CLAUDE_MODEL}."
    )
    grd.add_argument(
        "--provider",
        choices=[provider.value for provider in ModelProviderName],
        help="The model's provider, for --engine kiln.",
    )
    grd.add_argument(
        "--answer-style",
        choices=["structured_output", "submit_result"],
        help="For --engine kiln: how the agent hands back its result. Default: "
        "structured_output.",
    )
    grd.add_argument(
        "--prompt",
        type=Path,
        help="A grounding system prompt to try instead of the built-in one.",
    )
    grd.add_argument(
        "--cases", help="A subset of cases by index, e.g. 0,3-5. Default: all."
    )
    grd.add_argument(
        "--claude-bin", default="claude", help="The claude executable to run."
    )
    grd.add_argument(
        "--thinking-level",
        help="The grounding agent's thinking level: claude's --effort for --engine "
        "claude, the run config's thinking level for --engine kiln. Default: the "
        "model's own.",
    )
    grd.add_argument(
        "--task-id",
        help="With --run-config-id: the task whose run config lists the agent's tools.",
    )
    grd.add_argument(
        "--run-config-id",
        help="Describe the agent under test with this run config's tools, as the "
        "product does. Default: every tool the OpenEnv server has.",
    )
    grd.add_argument(
        "--claude-bare",
        action="store_true",
        help="Run claude with --bare: no CLAUDE.md, memory, hooks or plugins in the "
        "agent's context. It authenticates only with ANTHROPIC_API_KEY, not a Claude "
        "subscription. Without it, the user's own CLAUDE.md and memory still load.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None, *, claude_runner: ClaudeRunner = run_claude
) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            if args.count < 1:
                parser.error("--count must be at least 1.")
            asyncio.run(
                prepare(
                    PrepareArgs(
                        project=args.project,
                        task_id=args.task_id,
                        openenv_server_id=args.openenv_server_id,
                        spec=args.spec,
                        base_guidance=args.base_guidance,
                        data_guide=args.data_guide,
                        count=args.count,
                        out=args.out,
                    ),
                    copilot_api_key=get_copilot_api_key(),
                )
            )
            return 0
        if args.engine == "claude" and (
            args.provider is not None or args.answer_style is not None
        ):
            parser.error("--provider and --answer-style apply to --engine kiln only.")
        if args.engine == "kiln" and (args.model is None or args.provider is None):
            parser.error("--engine kiln needs --model and --provider.")
        return asyncio.run(
            ground(
                GroundArgs(
                    project=args.project,
                    openenv_server_id=args.openenv_server_id,
                    in_dir=args.in_dir,
                    out=args.out,
                    engine=args.engine,
                    model=args.model,
                    provider=ModelProviderName(args.provider)
                    if args.provider is not None
                    else None,
                    answer_style=args.answer_style or "structured_output",
                    prompt=args.prompt,
                    cases=args.cases,
                    claude_bin=args.claude_bin,
                    claude_bare=args.claude_bare,
                    thinking_level=args.thinking_level,
                    task_id=args.task_id,
                    run_config_id=args.run_config_id,
                ),
                claude_runner=claude_runner,
            )
        )
    except HTTPException as e:
        _progress(f"kiln_server: {e.detail}")
    except (GroundingSetupError, OpenEnvError, SyntheticUserError) as e:
        _progress(str(e))
    return 1


if __name__ == "__main__":
    sys.exit(main())
