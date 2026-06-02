"""Batch runner — fans drive_case out across N cases, streams BatchEvents.

`run_cases_batch` is an async generator yielding typed events so the
upcoming SSE endpoint can map each to a `data:` frame without
re-instrumenting. Cases run concurrently under an asyncio.Semaphore.

Responsibilities owned here (not in drive_case):
- Building the per-case `SyntheticUserDriver` (catches malformed
  `synthetic_user_info` blob → `CaseFailedEvent` for that case only).
- Building the per-case `TargetInvoker` that wraps `adapter.invoke` with
  the SU-attribution `input_source` — opaque blob on the root run, slim
  `{batch_tag, turn_index}` on subsequent turns.
- Tagging the leaf TaskRun for downstream eval-dataset discovery.
- Per-case error isolation (typed driver / loop / unexpected exceptions
  → `CaseFailedEvent` without affecting other in-flight cases).
- Bounded cleanup on consumer disconnect — case tasks are cancelled
  before the closer awaits them, so a browser disconnect doesn't keep
  the request alive for the duration of every in-flight case.
"""

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass
from typing import AsyncIterator

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_output import DataSource, DataSourceType
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.synthetic_user.driver import SyntheticUserDriver
from kiln_ai.synthetic_user.models import SyntheticUserDriverConfig
from kiln_ai.synthetic_user.parser import SyntheticUserInfoParseError
from kiln_ai.utils.git_sync_protocols import SaveContext, default_save_context
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam

from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    SyntheticUserCase,
)
from app.desktop.studio_server.synthetic_user.drive_loop import (
    TargetInvoker,
    drive_case,
)

logger = logging.getLogger(__name__)

# Module constants. Sized for an MVP beta — easy to bump in one place.
NUM_CASES_MAX = 10
DEFAULT_TURNS = 5
CONCURRENCY = 4

# Tag scheme. `_TAG_SU_CASE` lets the dataset view filter to all SU-generated
# leaves; `_TAG_PREFIX_SU_BATCH` (+ batch_tag) groups one batch for review.
_TAG_SU_CASE = "synthetic_user_case"
_TAG_PREFIX_SU_BATCH = "synthetic_user_batch:"

# Identifies this code path in `input_source.properties.adapter_name` so a
# reader looking at a TaskRun can tell who created it.
_RUNNER_ADAPTER_NAME = "kiln_synthetic_user_runner"


# ───────────────────────── BatchEvent dataclasses ─────────────────────────


@dataclass(frozen=True)
class BatchStartedEvent:
    batch_tag: str
    num_cases: int


@dataclass(frozen=True)
class TurnCompletedEvent:
    case_index: int
    assistant_run_id: str
    su_next_message: str
    cumulative_cost: float
    # Cumulative OpenAI-format trace at this point (system + all turns so far).
    # Lets the UI render the live conversation without a follow-up fetch.
    trace: list[ChatCompletionMessageParam]


@dataclass(frozen=True)
class CaseCompletedEvent:
    case_index: int
    chain_run_ids: list[str]
    leaf_run_id: str
    total_turns: int
    # Sum of the target adapter's cumulative_usage.cost across this case's
    # turns. Excludes the SU driver's per-turn LLM spend — SU turns run via
    # invoke_returning_run_output and never persist a TaskRun, so their cost
    # isn't rolled up here. Rename in mind for when SU cost gets threaded.
    target_total_cost: float


@dataclass(frozen=True)
class CaseFailedEvent:
    case_index: int
    error_code: str
    message: str


@dataclass(frozen=True)
class BatchCompletedEvent:
    successful: int
    failed: int
    batch_tag: str
    # Sum of CaseCompletedEvent.target_total_cost across successful cases.
    # Same SU-exclusion caveat applies.
    target_total_cost: float


BatchEvent = (
    BatchStartedEvent
    | TurnCompletedEvent
    | CaseCompletedEvent
    | CaseFailedEvent
    | BatchCompletedEvent
)


# ───────────────────────── public entry point ─────────────────────────


async def run_cases_batch(
    *,
    cases: list[SyntheticUserCase],
    target_task: Task,
    target_run_config: KilnAgentRunConfigProperties,
    su_driver_config: SyntheticUserDriverConfig,
    turns: int = DEFAULT_TURNS,
    concurrency: int = CONCURRENCY,
    batch_tag: str | None = None,
    save_context: SaveContext | None = None,
) -> AsyncIterator[BatchEvent]:
    """Drive `cases` concurrently against `target_task`, streaming progress.

    Each case runs in its own coroutine under an `asyncio.Semaphore` so the
    target-task LLM and the SU LLM aren't both hammered at unbounded fan-out.
    Events from different cases interleave; ordering WITHIN a case is
    `turn_completed`* → `case_completed | case_failed`.

    `save_context` wraps the leaf-tag save (the one write this runner
    controls). The adapter's per-turn `run.save_to_file()` inside
    `adapter.invoke` does NOT take a save_context — that's a kiln_ai-side
    plumbing gap shared with the chat SSE pattern, not specific to this
    runner. The route still uses `@no_write_lock` because wrapping the
    full streaming response in one atomic_write would block all other
    writes for the batch duration.

    Yields:
      BatchStartedEvent — once, before any case runs.
      TurnCompletedEvent — one per assistant turn within a case.
      CaseCompletedEvent — one per case that ran to completion.
      CaseFailedEvent — one per case that hit a typed error.
      BatchCompletedEvent — once, after all cases finish.
    """
    if not cases:
        raise ValueError("cases cannot be empty")
    if turns < 1:
        raise ValueError("turns must be >= 1")
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")

    resolved_batch_tag = batch_tag or _new_batch_tag()
    save_ctx: SaveContext = save_context or default_save_context
    semaphore = asyncio.Semaphore(concurrency)
    # `None` is the end-of-stream sentinel pushed when all cases finish.
    queue: asyncio.Queue[BatchEvent | None] = asyncio.Queue()

    async def _drive_one(case_index: int, case: SyntheticUserCase) -> None:
        async with semaphore:
            await _drive_one_case_and_emit(
                case_index=case_index,
                case=case,
                target_task=target_task,
                target_run_config=target_run_config,
                su_driver_config=su_driver_config,
                turns=turns,
                batch_tag=resolved_batch_tag,
                queue=queue,
                save_ctx=save_ctx,
            )

    # Kick the cases off BEFORE the first yield so they start running
    # concurrently with consumer setup. If the consumer disconnects between
    # BatchStartedEvent and the drain loop, the `finally` below still
    # cancels them.
    case_tasks = [asyncio.create_task(_drive_one(i, c)) for i, c in enumerate(cases)]

    async def _close_when_done() -> None:
        # `return_exceptions=True` so a stray bug doesn't leave the queue
        # draining forever; we surface failures via per-case CaseFailedEvent.
        await asyncio.gather(*case_tasks, return_exceptions=True)
        await queue.put(None)

    closer = asyncio.create_task(_close_when_done())

    successful = 0
    failed = 0
    target_total_cost = 0.0
    try:
        yield BatchStartedEvent(batch_tag=resolved_batch_tag, num_cases=len(cases))

        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
            if isinstance(event, CaseCompletedEvent):
                successful += 1
                target_total_cost += event.target_total_cost
            elif isinstance(event, CaseFailedEvent):
                failed += 1

        yield BatchCompletedEvent(
            successful=successful,
            failed=failed,
            batch_tag=resolved_batch_tag,
            target_total_cost=target_total_cost,
        )
    finally:
        # Cancel any in-flight case tasks before awaiting the closer. Without
        # this, a consumer disconnect (e.g. browser closes the SSE) leaves
        # workers running to completion writing to a dead queue — the request
        # stays "alive" for the full duration of every case.
        for task in case_tasks:
            if not task.done():
                task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await closer


# ───────────────────────── per-case orchestration ─────────────────────────


async def _drive_one_case_and_emit(
    *,
    case_index: int,
    case: SyntheticUserCase,
    target_task: Task,
    target_run_config: KilnAgentRunConfigProperties,
    su_driver_config: SyntheticUserDriverConfig,
    turns: int,
    batch_tag: str,
    queue: asyncio.Queue[BatchEvent | None],
    save_ctx: SaveContext,
) -> None:
    """Run drive_case for one case, translating per-turn outcomes to events
    on `queue` and ending with either CaseCompletedEvent or CaseFailedEvent.

    All upstream work — SyntheticUserDriver construction, target_invoker
    construction, drive_case execution, leaf tagging — runs inside a single
    try/except so any failure surfaces as a CaseFailedEvent rather than
    escaping into `asyncio.gather(return_exceptions=True)` (which would
    silently drop the case from the event stream).
    """
    try:
        # Construct the per-case SU driver. Parses the blob immediately;
        # a malformed blob fails this case without affecting others.
        try:
            su_driver = SyntheticUserDriver(case.synthetic_user_info, su_driver_config)
        except SyntheticUserInfoParseError as e:
            await queue.put(
                CaseFailedEvent(
                    case_index=case_index,
                    error_code="bad_synthetic_user_info",
                    message=str(e),
                )
            )
            return

        target_invoker = _make_target_invoker(
            case=case,
            target_task=target_task,
            target_run_config=target_run_config,
            su_driver_config=su_driver_config,
            batch_tag=batch_tag,
        )

        async def _on_turn(*, run: TaskRun, su_message: str) -> None:
            await queue.put(
                TurnCompletedEvent(
                    case_index=case_index,
                    assistant_run_id=str(run.id) if run.id is not None else "",
                    su_next_message=su_message,
                    cumulative_cost=_cumulative_cost(run),
                    # Snapshot the cumulative trace so the UI can render
                    # the live conversation without a follow-up fetch.
                    trace=list(run.trace) if run.trace else [],
                )
            )

        result = await drive_case(
            case=case,
            target_invoker=target_invoker,
            su_driver=su_driver,
            turns=turns,
            on_turn=_on_turn,
        )

        # Tag the leaf so eval-time loaders can find it. Inside the try
        # so a tag-save failure (full disk, validator rejection on a
        # malformed batch_tag) surfaces as case_failed, not a silent drop.
        leaf = result.chain[-1]
        async with save_ctx():
            _tag_leaf(leaf, batch_tag)

        await queue.put(
            CaseCompletedEvent(
                case_index=case_index,
                chain_run_ids=[
                    str(r.id) if r.id is not None else "" for r in result.chain
                ],
                leaf_run_id=str(leaf.id) if leaf.id is not None else "",
                total_turns=len(result.chain),
                target_total_cost=_cumulative_cost(leaf),
            )
        )
    except Exception as e:  # noqa: BLE001 — beta error surface
        # Adapter network errors, model misconfig, save_to_file blow-up,
        # anything unexpected. Log with full traceback; emit a structured
        # failure so the batch invariant holds (every case gets one event).
        logger.exception(
            "synthetic_user runner: unexpected error in case %d", case_index
        )
        await queue.put(
            CaseFailedEvent(
                case_index=case_index,
                error_code="unexpected_error",
                message=f"{type(e).__name__}: {e}",
            )
        )


# ───────────────────────── target invoker construction ─────────────────────


def _make_target_invoker(
    *,
    case: SyntheticUserCase,
    target_task: Task,
    target_run_config: KilnAgentRunConfigProperties,
    su_driver_config: SyntheticUserDriverConfig,
    batch_tag: str,
) -> TargetInvoker:
    """Build a per-case TargetInvoker over the real adapter.

    The closure tracks `turn_index` so the root run carries the full SU
    attribution context in `input_source.properties` while subsequent
    runs carry only the slim `{batch_tag, turn_index}` — the case is
    recoverable by walking `parent_task_run_id` to the root.
    """
    adapter = adapter_for_task(target_task, target_run_config)
    turn_index = 0

    async def _invoker(
        *,
        input: str,
        prior_trace: list[ChatCompletionMessageParam] | None,
        parent_task_run: TaskRun | None,
    ) -> TaskRun:
        nonlocal turn_index
        turn_index += 1
        input_source = _build_input_source(
            case=case,
            su_driver_config=su_driver_config,
            batch_tag=batch_tag,
            turn_index=turn_index,
            is_root=(turn_index == 1),
        )
        return await adapter.invoke(
            input=input,
            input_source=input_source,
            prior_trace=prior_trace,
            parent_task_run=parent_task_run,
        )

    return _invoker


def _build_input_source(
    *,
    case: SyntheticUserCase,
    su_driver_config: SyntheticUserDriverConfig,
    batch_tag: str,
    turn_index: int,
    is_root: bool,
) -> DataSource:
    """Attribute the user-side input on this turn to the SU driver model.

    Reuses `DataSourceType.synthetic` (a model produced this text) rather
    than inventing a new type — the existing validator accepts arbitrary
    extra property keys alongside the required `model_name` /
    `model_provider` / `adapter_name`.

    Root run carries the full opaque blob + seed_prompt so anyone landing
    on this run can recover the case context without walking the chain.
    Subsequent runs carry only the slim batch_tag/turn_index pair.
    """
    props: dict[str, str | int | float] = {
        "model_name": su_driver_config.model_name,
        "model_provider": su_driver_config.model_provider_name.value,
        "adapter_name": _RUNNER_ADAPTER_NAME,
        "batch_tag": batch_tag,
        "turn_index": turn_index,
    }
    if is_root:
        props["synthetic_user_info"] = case.synthetic_user_info
        props["seed_prompt"] = case.seed_prompt

    # The validator rejects empty string property values. Strip any that
    # would trip it (shouldn't happen for required fields in practice, but
    # this protects against an empty seed_prompt or a malformed config).
    filtered = {k: v for k, v in props.items() if not (isinstance(v, str) and v == "")}
    return DataSource(type=DataSourceType.synthetic, properties=filtered)


# ───────────────────────── small utilities ─────────────────────────


def _new_batch_tag() -> str:
    """12-char hex tag from uuid4 — short enough to read; long enough to
    avoid collisions across batches a user runs in the same session.
    """
    return uuid.uuid4().hex[:12]


def _cumulative_cost(run: TaskRun) -> float:
    """Read the rolled-up cost from a TaskRun, defaulting to 0 if usage is
    missing (defensive against fakes in unit tests that don't populate it).
    """
    usage = getattr(run, "cumulative_usage", None)
    if usage is None:
        return 0.0
    return float(getattr(usage, "cost", None) or 0.0)


def _tag_leaf(leaf: TaskRun, batch_tag: str) -> None:
    """Add the runner's discovery tags to the leaf TaskRun and persist.

    Tags are deduplicated (treated as a set then sorted) so re-runs
    against an already-tagged leaf are idempotent. A save_to_file
    exception surfaces to the caller (which converts to CaseFailedEvent).
    """
    tags = set(leaf.tags or [])
    tags.add(_TAG_SU_CASE)
    tags.add(f"{_TAG_PREFIX_SU_BATCH}{batch_tag}")
    leaf.tags = sorted(tags)
    leaf.save_to_file()
