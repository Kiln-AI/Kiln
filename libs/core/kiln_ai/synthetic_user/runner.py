"""Batch runner — fans drive_case out across N cases, streams BatchEvents.

`run_cases_batch` is an async generator yielding typed events. Cases run
concurrently under an asyncio.Semaphore. Per-case failures surface as
`CaseFailedEvent` without affecting other in-flight cases.
"""

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass
from typing import AsyncIterator

from kiln_ai.adapters.adapter_registry import adapter_for_task, load_skills_for_task
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, SkillsDict
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_output import DataSource, DataSourceType
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.synthetic_user.case import SyntheticUserCase
from kiln_ai.synthetic_user.drive_loop import TargetInvoker, drive_case
from kiln_ai.synthetic_user.driver import SyntheticUserDriver
from kiln_ai.synthetic_user.models import SyntheticUserDriverConfig
from kiln_ai.synthetic_user.parser import (
    SyntheticUserInfoParseError,
    parse_synthetic_user_info,
)
from kiln_ai.utils.git_sync_protocols import SaveContext, default_save_context
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam

logger = logging.getLogger(__name__)

# Module constants.
NUM_CASES_MAX = 10
MAX_TURNS_DEFAULT = 5
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
    # Target adapter cost + SU driver cost for this case.
    total_cost: float


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
    # Sum of CaseCompletedEvent.total_cost across successful cases.
    total_cost: float


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
    turns: int = MAX_TURNS_DEFAULT,
    concurrency: int = CONCURRENCY,
    batch_tag: str | None = None,
    save_context: SaveContext | None = None,
    task_run_config_id: str | None = None,
) -> AsyncIterator[BatchEvent]:
    """Drive `cases` concurrently against `target_task`, streaming progress.

    Each case runs in its own coroutine under an `asyncio.Semaphore` so the
    target-task LLM and the SU LLM aren't both hammered at unbounded fan-out.
    Events from different cases interleave; ordering WITHIN a case is
    `turn_completed`* → `case_completed | case_failed`.

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
    # Skills referenced by the run config must be pre-loaded at the
    # orchestration layer and injected via AdapterConfig — the adapter
    # raises if it meets a skill tool id with no injected dict. One
    # directory scan covers the whole batch.
    skills = load_skills_for_task(target_task, target_run_config)
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
                skills=skills,
                task_run_config_id=task_run_config_id,
            )

    # Kick the cases off BEFORE the first yield so they start running
    # concurrently with consumer setup. If the consumer disconnects between
    # BatchStartedEvent and the drain loop, the `finally` below still
    # cancels them. Tasks are named so asyncio debug dumps and pending-
    # task warnings point at this code path.
    case_tasks = [
        asyncio.create_task(
            _drive_one(i, c), name=f"su_case_{i}_{resolved_batch_tag[:6]}"
        )
        for i, c in enumerate(cases)
    ]

    async def _close_when_done() -> None:
        # `return_exceptions=True` so a stray bug doesn't leave the queue
        # draining forever; we surface failures via per-case CaseFailedEvent.
        # On the cancel path (consumer disconnect), the drain loop has
        # already exited, so the final `put(None)` is into-the-void —
        # harmless because the queue is unbounded and never re-read.
        await asyncio.gather(*case_tasks, return_exceptions=True)
        await queue.put(None)

    closer = asyncio.create_task(
        _close_when_done(), name=f"su_closer_{resolved_batch_tag[:6]}"
    )

    successful = 0
    failed = 0
    total_cost = 0.0
    try:
        yield BatchStartedEvent(batch_tag=resolved_batch_tag, num_cases=len(cases))

        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
            if isinstance(event, CaseCompletedEvent):
                successful += 1
                total_cost += event.total_cost
            elif isinstance(event, CaseFailedEvent):
                failed += 1

        yield BatchCompletedEvent(
            successful=successful,
            failed=failed,
            batch_tag=resolved_batch_tag,
            total_cost=total_cost,
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
    skills: SkillsDict,
    task_run_config_id: str | None,
) -> None:
    """Run drive_case for one case, emitting events on `queue`.

    Everything runs inside a single try/except so any failure surfaces as
    a CaseFailedEvent rather than silently dropping the case.
    """
    # Runs persist per turn (adapter autosave) but the batch tag only lands
    # on the leaf after a successful drive, so a mid-drive failure would
    # strand an untagged chain that no eval loader or delete-on-redrive
    # sweep can ever find. Track what this case persisted so the failure
    # arm can remove it.
    persisted_runs: dict[str, TaskRun] = {}
    try:
        # Malformed blob fails this case without affecting others.
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
            skills=skills,
            task_run_config_id=task_run_config_id,
        )

        async def _on_turn(*, run: TaskRun, su_message: str) -> None:
            if run.id is not None:
                persisted_runs[str(run.id)] = run
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
                total_cost=_cumulative_cost(leaf) + result.su_total_cost,
            )
        )
    except Exception as e:
        # Adapter network errors, model misconfig, save_to_file blow-up,
        # anything unexpected. Log with full traceback; emit a structured
        # failure so the batch invariant holds (every case gets one event).
        logger.exception(
            "synthetic_user runner: unexpected error in case %d", case_index
        )
        await _delete_partial_chain(persisted_runs, save_ctx)
        await queue.put(
            CaseFailedEvent(
                case_index=case_index,
                error_code="unexpected_error",
                message=f"{type(e).__name__}: {e}",
            )
        )


async def _delete_partial_chain(
    persisted_runs: dict[str, TaskRun], save_ctx: SaveContext
) -> None:
    """Best-effort removal of a failed case's partially-driven chain.

    A chain only becomes discoverable through the leaf's batch tag, applied
    after a successful drive — runs a failed case persisted would otherwise
    be permanent on-disk orphans. Never raises: the case failure already on
    the queue is the event that matters.
    """
    if not persisted_runs:
        return
    try:
        async with save_ctx():
            # Newest first: remove the dangling end of the chain before its
            # ancestors so an interrupted cleanup can't orphan a child run.
            for run in reversed(list(persisted_runs.values())):
                run.delete()
    except Exception:
        logger.exception(
            "synthetic_user runner: failed to clean up a failed case's "
            "partial chain (%d runs)",
            len(persisted_runs),
        )


# ───────────────────────── target invoker construction ─────────────────────


def _make_target_invoker(
    *,
    case: SyntheticUserCase,
    target_task: Task,
    target_run_config: KilnAgentRunConfigProperties,
    su_driver_config: SyntheticUserDriverConfig,
    batch_tag: str,
    skills: SkillsDict,
    task_run_config_id: str | None,
) -> TargetInvoker:
    """Build a per-case TargetInvoker over the real adapter.

    The closure tracks `turn_index` so the root run carries the full SU
    attribution context in `input_source.properties` while subsequent
    runs carry only the slim `{batch_tag, turn_index}` — the case is
    recoverable by walking `parent_task_run_id` to the root.

    Concurrency: the returned closure is NOT safe to invoke concurrently.
    `nonlocal turn_index` is incremented per call; concurrent callers
    would race on the increment and the resulting `is_root` flag.
    `drive_case` calls it sequentially within a single case (the
    `for _ in range(turns)` loop), which is the contract; cases are
    isolated by having their own closure with their own `turn_index`.
    """
    adapter = adapter_for_task(
        target_task,
        target_run_config,
        # task_run_config_id stamps each run's output source with the saved
        # config it came from, exactly as a manual run of that config would.
        base_adapter_config=AdapterConfig(
            skills=skills, task_run_config_id=task_run_config_id
        ),
    )
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

    Root run carries the decomposed case context (persona / goal /
    behavior_guidance / seed_prompt). Subsequent runs carry only the slim
    batch_tag/turn_index pair — full context is recoverable by walking
    parent_task_run_id to the root.
    """
    props: dict[str, str | int | float] = {
        "model_name": su_driver_config.model_name,
        "model_provider": su_driver_config.model_provider_name.value,
        "adapter_name": _RUNNER_ADAPTER_NAME,
        "batch_tag": batch_tag,
        "turn_index": turn_index,
    }
    if is_root:
        # Parse is cheap (regex on a short string) and was already
        # validated when the SU driver was built — re-parsing here can't
        # surface a new error class.
        info = parse_synthetic_user_info(case.synthetic_user_info)
        props["persona"] = info.persona
        props["goal"] = info.goal
        if info.behavior_guidance:
            props["behavior_guidance"] = info.behavior_guidance
        props["seed_prompt"] = case.seed_prompt

    return DataSource(type=DataSourceType.synthetic, properties=props)


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

    Reentrancy: the read-modify-write on `leaf.tags` assumes a single
    writer per leaf. The current call shape guarantees this (each case
    has its own leaf), so concurrent tagging across cases hits four
    different files. A future refactor that shares leaves across cases
    would need to re-introduce locking here.
    """
    tags = set(leaf.tags or [])
    tags.add(_TAG_SU_CASE)
    tags.add(f"{_TAG_PREFIX_SU_BATCH}{batch_tag}")
    leaf.tags = sorted(tags)
    leaf.save_to_file()
