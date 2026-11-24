"""One case, end to end: the grounding agent on a Kiln model, through Kiln's adapter."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import JsonValue, ValidationError

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.errors import (
    EMPTY_RESPONSE_ERROR_MESSAGE,
    KilnRunError,
    StructuredOutputParseError,
)
from kiln_ai.adapters.ml_model_list import (
    default_structured_output_mode_for_model_provider,
)
from kiln_ai.adapters.model_adapters.adapter_stream import CONTENT_FILTER_ERROR_MESSAGE
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.adapters.model_adapters.litellm_adapter import MAX_TOOL_CALLS_PER_TURN
from kiln_ai.adapters.retry_classification import unwrap_kiln_run_error
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.openenv import OpenEnvServer, OpenEnvTool
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_output import TASK_OUTPUT_SCHEMA_ERROR_PREFIX
from kiln_ai.datamodel.tool_id import build_kiln_unmanaged_tool_id
from kiln_ai.eval_grounding.models import (
    DropReason,
    EvalContext,
    GroundingCase,
    GroundingMode,
    GroundingOutcome,
    GroundingResult,
    result_json_schema,
)
from kiln_ai.eval_grounding.prompt import (
    KilnAnswerStyle,
    case_message,
    follow_up_message,
    system_prompt,
)
from kiln_ai.eval_grounding.session import (
    DEFAULT_LIMITS,
    DEFAULT_TIME_LIMIT_S,
    SUBMIT_RESULT_TOOL,
    GroundingLimitReached,
    GroundingLimits,
    GroundingSession,
)
from kiln_ai.openenv.session_manager import (
    OpenEnvError,
    OpenEnvSessionManager,
)
from kiln_ai.tools.base_tool import (
    ToolCallContext,
    ToolCallDefinition,
    ToolCallError,
    ToolCallResult,
    UnmanagedKilnTool,
)
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam
from kiln_ai.utils.usage import Usage

NO_SUBMISSION_ERROR = f"You ended without calling {SUBMIT_RESULT_TOOL}."
"""Why a `submit_result` run's reply could not be used, when the tool was never called."""

MAX_INVALID_SUBMISSIONS = 2
"""Invalid `submit_result` calls before the case drops: the first gets its error back."""


def time_limit_detail(time_limit_s: float) -> str:
    """The `drop_detail` of a case that ran out of time."""
    return f"The agent ran past the {time_limit_s / 60:g} minute limit."


async def ground_case(
    case: GroundingCase,
    *,
    eval_context: EvalContext,
    openenv_server: OpenEnvServer,
    session_manager: OpenEnvSessionManager,
    server_tools: Sequence[OpenEnvTool],
    model_name: str,
    model_provider: ModelProviderName,
    target_tools: list[ToolCallDefinition],
    reset_schema: dict[str, JsonValue] | None,
    thinking_level: str | None = None,
    answer_style: KilnAnswerStyle = "structured_output",
    system_prompt_text: str | None = None,
    limits: GroundingLimits = DEFAULT_LIMITS,
    time_limit_s: float = DEFAULT_TIME_LIMIT_S,
) -> GroundingOutcome:
    """Ground one case on the given model, or drop it.

    `server_tools` are the OpenEnv server's tools, which the agent gets; `target_tools`
    are what the agent under test can call, which the agent is told about. Errors that
    are not the case's fault (the environment failing, the model provider failing) are
    raised, unless a `submit_result` call already recorded the result, which is kept.
    An adapter error the model caused (an empty reply, too many tool rounds) drops the
    case. The case's episode is released on every exit, cancellation included."""
    message = case_message(
        case,
        eval_context=eval_context,
        reset_schema=reset_schema,
        target_tools=target_tools,
    )
    session = GroundingSession(openenv_server, session_manager, server_tools, limits)
    submit_tool = (
        _SubmitResultTool(session, eval_context)
        if answer_style == "submit_result"
        else None
    )
    adapter = _build_adapter(
        session,
        submit_tool,
        model_name=model_name,
        model_provider=model_provider,
        thinking_level=thinking_level,
        mode=eval_context.mode,
        instruction=system_prompt_text
        or system_prompt(limits, time_limit_s, answer_style, eval_context.mode),
    )
    run = _GroundingRun(session, adapter, submit_tool, eval_context)
    try:
        # asyncio.wait_for, not asyncio.timeout: libs/core supports Python 3.10.
        return await asyncio.wait_for(run.ground(message), timeout=time_limit_s)
    except asyncio.TimeoutError:
        return GroundingOutcome.dropped(
            DropReason.limit,
            time_limit_detail(time_limit_s),
            call_log=session.call_log,
            usage=run.usage,
            usage_complete=False,
        )
    finally:
        await session.close()


def _build_adapter(
    session: GroundingSession,
    submit_tool: _SubmitResultTool | None,
    *,
    model_name: str,
    model_provider: ModelProviderName,
    thinking_level: str | None,
    mode: GroundingMode,
    instruction: str,
) -> BaseAdapter:
    structured = submit_tool is None
    task = Task(
        name="grounding_agent",
        description="In-memory grounding agent. Not persisted.",
        instruction=instruction,
        output_json_schema=json.dumps(
            result_json_schema(args_as_json_string=True, mode=mode),
            ensure_ascii=False,
        )
        if structured
        else None,
    )
    run_config = KilnAgentRunConfigProperties(
        model_name=model_name,
        model_provider_name=model_provider,
        prompt_id=PromptGenerators.SIMPLE,
        structured_output_mode=structured_output_mode(model_name, model_provider)
        if structured
        else StructuredOutputMode.default,
        tools_config=ToolsRunConfig(tools=[]),
        thinking_level=thinking_level,
    )
    return adapter_for_task(
        task,
        run_config,
        AdapterConfig(
            allow_saving=False,
            unmanaged_tools=[*session.tools(), *([submit_tool] if submit_tool else [])],
            open_openenv_session=False,
            # Each tool round re-sends the whole conversation; caching the prefix
            # keeps a case from paying full price for it on every call.
            automatic_prompt_caching=True,
        ),
    )


def structured_output_mode(
    model_name: str, model_provider: ModelProviderName
) -> StructuredOutputMode:
    """The model's listed structured output mode, unless it returns the result as a tool
    call: the adapter refuses that alongside other tools, and `default` picks it for
    most providers. Those fall back to a JSON schema response format."""
    return default_structured_output_mode_for_model_provider(
        model_name,
        model_provider,
        default=StructuredOutputMode.json_schema,
        disallowed_modes=[
            StructuredOutputMode.function_calling,
            StructuredOutputMode.function_calling_weak,
            StructuredOutputMode.default,
            StructuredOutputMode.unknown,
        ],
    )


@dataclass(frozen=True)
class _Reply:
    """How one adapter call ended, short of a stop. `output` is None when the adapter
    refused the model's final answer; `trace` is what a follow-up continues from."""

    output: object | None
    trace: list[ChatCompletionMessageParam] | None
    error: str | None


class _GroundingRun:
    """The adapter calls for one case: the first, and at most one follow-up asking only
    for the result."""

    def __init__(
        self,
        session: GroundingSession,
        adapter: BaseAdapter,
        submit_tool: _SubmitResultTool | None,
        eval_context: EvalContext,
    ) -> None:
        self._session = session
        self._adapter = adapter
        self._submit_tool = submit_tool
        self._eval_context = eval_context
        self.usage: Usage | None = None
        # Kiln's adapter reports a run's usage only when the run returns, so a run that
        # is cancelled or raises leaves its calls out of `usage`.
        self.usage_complete = True

    async def ground(self, message: str) -> GroundingOutcome:
        try:
            return await self._ground(message)
        except _ModelMisbehaved as e:
            return GroundingOutcome.dropped(
                e.reason,
                e.detail,
                call_log=self._session.call_log,
                usage=self.usage,
                usage_complete=self.usage_complete,
            )

    async def _ground(self, message: str) -> GroundingOutcome:
        reply = await self._invoke(message, prior_trace=None)
        if reply is None:
            return self._stopped_outcome()
        result, error = self._read_result(reply)
        if result is not None:
            return self._outcome(result)
        if error is None or reply.trace is None:
            return self._invalid_output(error)

        await self._session.close_tools()
        follow_up = await self._invoke(
            follow_up_message(error, self._answer_style), prior_trace=reply.trace
        )
        if follow_up is None:
            return self._stopped_outcome()
        result, follow_up_error = self._read_result(follow_up)
        if result is not None:
            return self._outcome(result)
        return self._invalid_output(follow_up_error or error)

    @property
    def _answer_style(self) -> KilnAnswerStyle:
        return "submit_result" if self._submit_tool else "structured_output"

    def _read_result(self, reply: _Reply) -> tuple[GroundingResult | None, str | None]:
        """The result, or why there is none. A None error means there is nothing a
        follow-up could fix."""
        if self._submit_tool is not None:
            if self._submit_tool.result is not None:
                return self._submit_tool.result, None
            if self._submit_tool.gave_up:
                return None, None
            return None, NO_SUBMISSION_ERROR
        if reply.output is None:
            return None, reply.error
        if not isinstance(reply.output, dict):
            return None, "The result is not a JSON object."
        try:
            result = GroundingResult.from_model_output(
                reply.output, args_as_json_string=True
            )
        except ValueError as e:
            return None, _describe_error(e)
        problem = result.problem_for(self._eval_context)
        if problem is not None:
            return None, problem
        return result, None

    async def _invoke(
        self, input: str, *, prior_trace: list[ChatCompletionMessageParam] | None
    ) -> _Reply | None:
        """One adapter call, cut short when the session stops. Returns None for the hard
        stop after a limit. Raises `_ModelMisbehaved` when the model's own behaviour
        ended the call, and re-raises environment and provider failures, unless a
        `submit_result` call already recorded the result, which is kept."""
        invoke = asyncio.ensure_future(
            self._adapter.invoke_returning_run_output(input, prior_trace=prior_trace)
        )
        stopped = asyncio.ensure_future(self._session.wait_until_stopped())
        try:
            await asyncio.wait({invoke, stopped}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for pending in (invoke, stopped):
                pending.cancel()
            await asyncio.gather(invoke, stopped, return_exceptions=True)

        stop = self._session.stop_error
        if stop is not None:
            self.usage_complete = False
        if isinstance(stop, GroundingLimitReached):
            return None
        if stop is not None:
            raise stop
        try:
            task_run, run_output = invoke.result()
        except KilnRunError as e:
            cause = unwrap_kiln_run_error(e)
            if self._submit_tool is not None and self._submit_tool.result is not None:
                self.usage_complete = False
                return _Reply(output=None, trace=None, error=None)
            if isinstance(cause, OpenEnvError):
                raise cause from e
            if _is_unusable_output_error(cause):
                self.usage_complete = False
                return _Reply(
                    output=None, trace=e.partial_trace, error=_describe_error(cause)
                )
            misbehaviour = _model_misbehaviour(cause)
            if misbehaviour is not None:
                self.usage_complete = False
                raise misbehaviour from e
            raise
        self._add_usage(task_run.usage)
        return _Reply(output=run_output.output, trace=task_run.trace, error=None)

    def _add_usage(self, usage: Usage | None) -> None:
        if usage is not None:
            self.usage = usage if self.usage is None else self.usage + usage

    def _outcome(self, result: GroundingResult) -> GroundingOutcome:
        return GroundingOutcome.from_result(
            result,
            openenv_reset=self._session.last_reset,
            call_log=self._session.call_log,
            usage=self.usage,
            usage_complete=self.usage_complete,
        )

    def _stopped_outcome(self) -> GroundingOutcome:
        if self._submit_tool is not None and self._submit_tool.result is not None:
            return self._outcome(self._submit_tool.result)
        return GroundingOutcome.dropped(
            DropReason.limit,
            str(self._session.stop_error),
            call_log=self._session.call_log,
            usage=self.usage,
            usage_complete=self.usage_complete,
        )

    def _invalid_output(self, error: str | None) -> GroundingOutcome:
        detail = (
            self._submit_tool.last_error
            if self._submit_tool is not None and self._submit_tool.gave_up
            else error
        ) or "the model's answer could not be read."
        return GroundingOutcome.dropped(
            DropReason.invalid_output,
            f"The agent's result could not be used: {detail}",
            call_log=self._session.call_log,
            usage=self.usage,
            usage_complete=self.usage_complete,
        )


class _SubmitResultTool(UnmanagedKilnTool):
    """The agent's way to hand back its result in the `submit_result` answer style.
    An accepted result closes the session's tools, so the environment it describes
    can't change afterwards."""

    def __init__(self, session: GroundingSession, eval_context: EvalContext) -> None:
        super().__init__(
            build_kiln_unmanaged_tool_id(f"grounding_{SUBMIT_RESULT_TOOL}"),
            SUBMIT_RESULT_TOOL,
            "Hand back your result for this case. Call it once, when you are done.",
            result_json_schema(args_as_json_string=False, mode=eval_context.mode),
        )
        self._session = session
        self._eval_context = eval_context
        self.result: GroundingResult | None = None
        self.last_error: str | None = None
        self._invalid_calls = 0

    @property
    def gave_up(self) -> bool:
        """True once the agent has sent `MAX_INVALID_SUBMISSIONS` invalid results."""
        return self._invalid_calls >= MAX_INVALID_SUBMISSIONS

    async def run(
        self, context: ToolCallContext | None = None, **kwargs: Any
    ) -> ToolCallResult:
        if self.result is not None:
            raise ToolCallError(
                "Your result is already recorded. Reply with only the word done."
            )
        if self.gave_up:
            raise ToolCallError(
                "Your result could not be used. Reply with only the word done."
            )
        try:
            result = GroundingResult.model_validate(kwargs)
        except ValidationError as e:
            raise await self._refuse(_describe_error(e)) from e
        problem = result.problem_for(self._eval_context)
        if problem is not None:
            raise await self._refuse(problem)
        self.result = result
        await self._session.close_tools()
        return ToolCallResult(output="Recorded. Reply with only the word done.")

    async def _refuse(self, error: str) -> ToolCallError:
        """The error for an invalid result, counting it. Once the agent has given up, the
        session's tools close and the agent is told to stop."""
        self._invalid_calls += 1
        self.last_error = error
        if self.gave_up:
            await self._session.close_tools()
            return ToolCallError(
                f"This result can't be used either: {error} "
                "Reply with only the word done."
            )
        return ToolCallError(
            f"This result can't be used: {error} Fix it and call "
            f"{SUBMIT_RESULT_TOOL} again."
        )


class _ModelMisbehaved(Exception):
    """The adapter stopped the run over something the model did, not the provider or
    the environment. Drops the one case."""

    def __init__(self, reason: DropReason, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


_CONTENT_FILTER_PREFIX = CONTENT_FILTER_ERROR_MESSAGE.split("{", 1)[0]


def _model_misbehaviour(error: BaseException) -> _ModelMisbehaved | None:
    """The drop for an adapter error the model caused, or None for any other error.
    The adapter raises these as plain ValueError and RuntimeError, so they are told
    apart by message."""
    message = str(error)
    unusable = "The agent's result could not be used: "
    if isinstance(error, ValueError):
        if message.startswith(EMPTY_RESPONSE_ERROR_MESSAGE):
            return _ModelMisbehaved(
                DropReason.invalid_output, unusable + "the model sent an empty reply."
            )
        if message.startswith(_CONTENT_FILTER_PREFIX):
            return _ModelMisbehaved(
                DropReason.invalid_output,
                unusable + "the model declined to respond.",
            )
    if isinstance(error, RuntimeError):
        if message.startswith("Model returned neither content nor tool calls"):
            return _ModelMisbehaved(
                DropReason.invalid_output, unusable + "the model sent an empty reply."
            )
        if message.startswith("Model asked for impossible combination"):
            return _ModelMisbehaved(
                DropReason.invalid_output,
                unusable + "the model tried to answer and call tools in the same turn.",
            )
        if message.startswith("Too many tool calls"):
            return _ModelMisbehaved(
                DropReason.limit,
                f"The agent made more than {MAX_TOOL_CALLS_PER_TURN} rounds of tool "
                "calls without finishing.",
            )
    return None


def _is_unusable_output_error(error: BaseException) -> bool:
    """The adapter refused the model's final answer: not JSON, or not the task's
    schema. A follow-up can fix these."""
    return isinstance(error, StructuredOutputParseError) or (
        isinstance(error, ValueError)
        and str(error).startswith(TASK_OUTPUT_SCHEMA_ERROR_PREFIX)
    )


def _describe_error(error: BaseException) -> str:
    """A short, one-line account of a validation failure, for the model and the user."""
    if isinstance(error, ValidationError):
        return "; ".join(
            f"{'.'.join(str(part) for part in e['loc']) or 'result'}: {e['msg']}"
            for e in error.errors(include_url=False)
        )
    return str(error).strip().splitlines()[0] if str(error).strip() else repr(error)
