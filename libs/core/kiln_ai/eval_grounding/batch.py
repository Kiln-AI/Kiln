"""Many cases, grounded concurrently, with a progress event per finished case."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass

from kiln_ai.adapters.retry_classification import (
    is_retryable_error,
    is_transient_openenv_error,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.eval_grounding.agent import ground_case
from kiln_ai.eval_grounding.models import EvalContext, GroundingCase, GroundingOutcome
from kiln_ai.eval_grounding.prompt import KilnAnswerStyle
from kiln_ai.eval_grounding.session import (
    DEFAULT_LIMITS,
    DEFAULT_TIME_LIMIT_S,
    GroundingLimits,
)
from kiln_ai.openenv.session_manager import OpenEnvSessionManager
from kiln_ai.synthetic_user.runner import CONCURRENCY
from kiln_ai.tools.base_tool import ToolCallDefinition
from kiln_ai.utils.async_job_runner import (
    AsyncJobRunner,
    AsyncJobRunnerObserver,
    RetryableError,
)
from kiln_ai.utils.usage import Usage

CASE_MAX_RETRIES = 2
"""Extra attempts a case gets after a transient provider or environment failure. Each
attempt starts the case over in a fresh episode."""

CASE_RETRY_DELAY_S = 5.0
"""Width of the first backoff window before a retry; the job runner widens it for each
later retry and waits a random time inside it."""


@dataclass(frozen=True)
class CaseGrounded:
    """One case finished, grounded or dropped."""

    case_index: int
    outcome: GroundingOutcome


@dataclass(frozen=True)
class GroundingFinished:
    """Every case finished. `usage` sums the cases that reported any;
    `usage_complete` is False when any case's usage is missing some model calls."""

    grounded: int
    dropped: int
    usage: Usage | None
    usage_complete: bool


GroundingProgress = CaseGrounded | GroundingFinished


class GroundingCaseError(Exception):
    """A case raised an error that is not the case's fault, which stopped the batch.
    `error` is what `ground_case` raised on its last attempt; `case_index` is the case's
    position in `cases`."""

    def __init__(self, case_index: int, error: Exception) -> None:
        super().__init__(f"Case {case_index}: {error}")
        self.case_index = case_index
        self.error = error


async def ground_cases(
    cases: Sequence[GroundingCase],
    *,
    eval_context: EvalContext,
    openenv_server: OpenEnvServer,
    session_manager: OpenEnvSessionManager,
    model_name: str,
    model_provider: ModelProviderName,
    target_tools: list[ToolCallDefinition],
    thinking_level: str | None = None,
    answer_style: KilnAnswerStyle = "structured_output",
    system_prompt_text: str | None = None,
    limits: GroundingLimits = DEFAULT_LIMITS,
    time_limit_s: float = DEFAULT_TIME_LIMIT_S,
    concurrency: int = CONCURRENCY,
    max_retries: int = CASE_MAX_RETRIES,
    retry_delay_s: float = CASE_RETRY_DELAY_S,
) -> AsyncGenerator[GroundingProgress, None]:
    """Ground `cases` at most `concurrency` at a time. Yields a `CaseGrounded` as each
    finishes, in finishing order, then a `GroundingFinished`.

    The server's reset schema, metadata and tools are read once, before the first case.
    A case that fails with a transient provider or environment error is started over,
    up to `max_retries` times with backoff; its outcome then reports incomplete usage,
    since the failed attempts' model calls are not in it. Any other error from a case
    (one that is not the case's fault), or a transient one that outlasts its retries,
    cancels the rest and waits for them to release their episodes, then is raised as a
    `GroundingCaseError`. Closing the generator early cancels the rest the same way."""
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    reset_schema = await session_manager.reset_schema(openenv_server)
    metadata = await session_manager.metadata(openenv_server)
    server_tools = await session_manager.list_tools(openenv_server)
    # None ends the stream once every case has finished.
    queue: asyncio.Queue[CaseGrounded | GroundingCaseError | None] = asyncio.Queue()
    # The job runner stops waiting for its cancelled workers as soon as the first one
    # ends, so each case runs in its own task, which teardown waits for in full.
    in_flight: set[asyncio.Task[GroundingOutcome]] = set()
    retried: set[int] = set()

    async def ground_one(job: tuple[int, GroundingCase]) -> bool:
        case_index, case = job
        case_task = asyncio.ensure_future(
            ground_case(
                case,
                eval_context=eval_context,
                openenv_server=openenv_server,
                session_manager=session_manager,
                server_tools=server_tools,
                model_name=model_name,
                model_provider=model_provider,
                thinking_level=thinking_level,
                target_tools=target_tools,
                reset_schema=reset_schema,
                metadata=metadata,
                answer_style=answer_style,
                system_prompt_text=system_prompt_text,
                limits=limits,
                time_limit_s=time_limit_s,
            )
        )
        in_flight.add(case_task)
        case_task.add_done_callback(in_flight.discard)
        try:
            outcome = await case_task
        except Exception as e:
            if is_retryable_error(e) or is_transient_openenv_error(e):
                retried.add(case_index)
                raise RetryableError(f"{type(e).__name__}: {e}") from e
            raise
        if case_index in retried:
            outcome = outcome.model_copy(update={"usage_complete": False})
        queue.put_nowait(CaseGrounded(case_index, outcome))
        return True

    class StopBatchOnError(AsyncJobRunnerObserver[tuple[int, GroundingCase]]):
        """Hands a case's final error to the consumer, which stops the batch. The job
        runner calls this once a case's retries are spent, and would otherwise only log
        the error and carry on."""

        async def on_error(self, job: tuple[int, GroundingCase], error: Exception):
            cause = error.__cause__ if isinstance(error, RetryableError) else error
            queue.put_nowait(
                GroundingCaseError(
                    job[0], cause if isinstance(cause, Exception) else error
                )
            )

    runner = AsyncJobRunner(
        jobs=list(enumerate(cases)),
        run_job_fn=ground_one,
        concurrency=concurrency,
        observers=[StopBatchOnError()],
        max_retries=max_retries,
        retry_delay=retry_delay_s,
    )

    async def run_all() -> None:
        try:
            async for _ in runner.run():
                pass
        finally:
            queue.put_nowait(None)

    jobs = asyncio.create_task(run_all(), name="ground_cases")
    grounded = 0
    dropped = 0
    usage: Usage | None = None
    usage_complete = True
    try:
        while (item := await queue.get()) is not None:
            if isinstance(item, GroundingCaseError):
                raise item from item.error
            usage_complete = usage_complete and item.outcome.usage_complete
            if item.outcome.status == "grounded":
                grounded += 1
            else:
                dropped += 1
            if item.outcome.usage is not None:
                usage = (
                    item.outcome.usage if usage is None else usage + item.outcome.usage
                )
            yield item
        yield GroundingFinished(
            grounded=grounded,
            dropped=dropped,
            usage=usage,
            usage_complete=usage_complete,
        )
    finally:
        jobs.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await jobs
        # A cancelled ground_case releases its episode before its task ends.
        await asyncio.gather(*in_flight, return_exceptions=True)
