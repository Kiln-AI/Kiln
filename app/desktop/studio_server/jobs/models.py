from __future__ import annotations

from collections.abc import Hashable
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    ClassVar,
    Generic,
    TypeVar,
)

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WaitTimeoutBounds:
    """Bounds for the multi-job wait endpoint's timeout (seconds).

    The wait is always bounded: it is a plain (non-streaming) handler, so a client
    that disconnects does not cancel it. An unbounded wait on a job that never
    terminates (for example, one the user paused) would hold the coroutine for the
    life of the process. A caller that wants to wait longer issues the wait again;
    504 means "still running", not failure.
    """

    DEFAULT = 600.0
    MAX = 3600.0


class BackgroundJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_STATUSES


TERMINAL_STATUSES = frozenset(
    {
        BackgroundJobStatus.SUCCEEDED,
        BackgroundJobStatus.FAILED,
        BackgroundJobStatus.CANCELLED,
    }
)

# Background jobs retry an item that fails with a transient provider error (rate
# limit, connection blip) more patiently than the interactive runners do. With
# AsyncJobRunner's backoff (each window 4x the last, full jitter) the three waits are
# drawn from 0-5s, 0-20s and 0-80s, so a throttled provider gets up to ~105s to
# recover before the item's error is reported.
JOB_TRANSIENT_ERROR_MAX_RETRIES = 3
JOB_TRANSIENT_ERROR_RETRY_DELAY_SECONDS = 5.0

# The most items a background job may process in parallel. Each item is at least
# one model call and holds a connection and its buffers while it waits, so an
# unbounded value lets one request open thousands of provider calls at once.
JOB_MAX_CONCURRENCY = 100


class JobProgress(BaseModel):
    """Count-based progress for a job.

    Processed = success + error; remaining = total - success - error. The error
    field is a count only — the actual messages live in the per-run error log.
    """

    total: int | None = Field(
        default=None,
        description="Total number of items to process, or null when the size is not yet known.",
    )
    success: int = Field(
        default=0, description="Number of items processed successfully so far."
    )
    error: int = Field(
        default=0,
        description="Number of items that failed so far. A count only — the actual "
        "messages live in the per-run error log.",
    )
    message: str | None = Field(
        default=None,
        description="Optional human-readable status line describing the current step.",
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp of the most recent progress update.",
    )


class JobDerivedState(BaseModel):
    """A worker's view of the operation's true state, read from source-of-truth entities."""

    total: int | None = Field(
        default=None,
        description="Total number of items to process, or null when the size is not yet known.",
    )
    success: int = Field(
        default=0,
        description="Number of items confirmed complete by reading source-of-truth entities.",
    )
    error: int | None = Field(
        default=None,
        description="Number of items confirmed failed by reading source-of-truth entities, "
        "or null when failures leave nothing on disk to count. Null keeps the error count "
        "the job reported while it ran.",
    )
    is_complete: bool = Field(
        default=False,
        description="Whether the operation is fully complete according to source-of-truth entities.",
    )
    message: str | None = Field(
        default=None,
        description="Optional human-readable status line describing the derived state.",
    )


class JobError(BaseModel):
    """Small failure summary stamped on the record. Detail lives in the error log."""

    error: str | None = Field(
        default=None,
        description="Short human-readable summary of why the job failed.",
    )
    detail: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured context for the failure. Fuller detail lives in the error log.",
    )


class JobRecord(BaseModel):
    """Ephemeral, in-memory bookkeeping for a single job. Never persisted to disk."""

    id: str = Field(description="Unique identifier for this job.")
    type: str = Field(
        description="Registered job type name, determining which worker runs it."
    )
    status: BackgroundJobStatus = Field(
        description="Current lifecycle status: pending, running, paused, succeeded, "
        "failed, or cancelled."
    )
    run_id: str | None = Field(
        default=None,
        description="Identifier of the current (or most recent) run attempt, used to "
        "locate its error log. Null before the job first starts.",
    )
    progress: JobProgress = Field(
        default_factory=JobProgress,
        description="Generic count-based progress snapshot for the job.",
    )
    # Typed, per-worker progress detail (validated against the worker's
    # `progress_model`). The generic `progress` above is the universal counter;
    # this carries the rich per-kind shape a worker needs the UI to render
    # (e.g. RAG's four-phase breakdown). Kept as a dict on the wire so the core
    # stays worker-agnostic; the frontend casts it to the worker's model.
    progress_detail: dict[str, Any] | None = Field(
        default=None,
        description="Optional typed, worker-specific progress detail (validated against "
        "the worker's progress_model). Null for workers whose generic count progress is enough.",
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description="Optional static, worker-published descriptive properties for this job "
        "(validated against the worker's properties_model). Derived once from params at "
        "create time and unchanged over the run.",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="The validated parameters this job was created with.",
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="The job's output, present only once it has succeeded. Null otherwise.",
    )
    error: JobError | None = Field(
        default=None,
        description="Failure summary, present only when the job has failed. Null otherwise.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form attribution passed in at creation, stored verbatim.",
    )
    project_id: str | None = Field(
        default=None,
        description="Project this job is scoped to, used for filtering and visibility.",
    )
    supports_pause: bool = Field(
        default=False,
        description="Whether this job type can be paused and resumed.",
    )
    created_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp of when the job was created.",
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp of the most recent change to the job record.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="UTC timestamp of when the job first started running. Null until it starts.",
    )
    ended_at: datetime | None = Field(
        default=None,
        description="UTC timestamp of when the job reached a terminal state. Null until it ends.",
    )


ReportProgress = Callable[["JobProgressUpdate"], Awaitable[None]]
ReportProgressDetail = Callable[[BaseModel], Awaitable[None]]
ReportError = Callable[[str, dict[str, Any]], Awaitable[None]]


class JobProgressUpdate(BaseModel):
    success: int = Field(
        description="Cumulative number of items processed successfully."
    )
    error: int = Field(default=0, description="Cumulative number of items that failed.")
    total: int | None = Field(
        default=None,
        description="Total number of items to process, or null when the size is not yet known.",
    )
    message: str | None = Field(
        default=None,
        description="Optional human-readable status line describing the current step.",
    )


class JobContext:
    """Provided to the worker by JobRegistry during run().

    Holds the current job_id and run_id, plus registry-injected callbacks for
    reporting progress (in-memory snapshot + event) and per-item errors (error log).
    """

    def __init__(
        self,
        job_id: str,
        run_id: str,
        report_progress: ReportProgress,
        report_progress_detail: ReportProgressDetail,
        report_error: ReportError,
    ) -> None:
        self.job_id = job_id
        self.run_id = run_id
        self._report_progress = report_progress
        self._report_progress_detail = report_progress_detail
        self._report_error = report_error

    async def report_progress(
        self,
        success: int,
        error: int = 0,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        """Update the registry's in-memory progress snapshot and emit an event.

        A UI-smoothing signal only — the authoritative progress comes from
        compute_state(). Cheap to call often.
        """
        await self._report_progress(
            JobProgressUpdate(
                success=success,
                error=error,
                total=total,
                message=message,
            )
        )

    async def report_progress_detail(self, detail: BaseModel) -> None:
        """Stamp the job's typed `progress_detail` with a worker-specific model.

        For rich per-kind progress the generic counter can't carry (e.g. RAG's
        per-phase breakdown). `detail` must be an instance of the worker's
        declared `progress_model`; the registry validates and serializes it.
        A UI-smoothing signal only — authoritative progress comes from
        compute_state(). Cheap to call often.
        """
        await self._report_progress_detail(detail)

    async def report_error(self, error_message: str, **extra: Any) -> None:
        """Append one structured error entry to this run's error log.

        For non-fatal per-item errors that don't stop the run. Best-effort: a
        failed write is swallowed, never propagated. Does not itself bump the
        progress error count — report that via report_progress.
        """
        await self._report_error(error_message, extra)


TParams = TypeVar("TParams", bound=BaseModel)
TResult = TypeVar("TResult", bound=BaseModel)


class JobWorker(Generic[TParams, TResult]):
    type_name: ClassVar[str]
    params_model: ClassVar[type[BaseModel]]
    result_model: ClassVar[type[BaseModel]]
    # Optional typed model for rich per-worker progress reported via
    # JobContext.report_progress_detail(); stamped on JobRecord.progress_detail.
    # Leave None for workers whose generic count progress is enough.
    progress_model: ClassVar[type[BaseModel] | None] = None
    # Optional typed model for static descriptive properties returned by
    # describe() and stamped on JobRecord.properties. Leave None for workers
    # that have nothing descriptive to publish.
    properties_model: ClassVar[type[BaseModel] | None] = None
    supports_pause: ClassVar[bool] = False
    # The dedicated endpoint that creates jobs of this type. When set, the generic
    # POST /api/jobs/{type} refuses the type, so the dedicated endpoint's request
    # checks and agent policy cannot be bypassed.
    create_path: ClassVar[str | None] = None
    # Whether the generic POST /api/jobs/{type} may create jobs of this type. That
    # route lets an agent create a job without approval, so a worker opts in only
    # when its jobs are safe to start that way (no model calls, no credit spend).
    # False by default: a new worker is refused there until someone decides
    # otherwise.
    generic_create_allowed: ClassVar[bool] = False

    def dedupe_key(self, params: TParams) -> Hashable | None:
        """Identify the work a job of this type would do, so the registry can return
        an unfinished job with the same key instead of starting a second one that
        would do the same work again. None (the default) never deduplicates.

        Must be pure and cheap: the registry calls it inside create(), between its
        last await and the job's insertion.
        """
        return None

    async def describe(self, params: TParams) -> BaseModel | None:
        """Return static, worker-specific descriptive properties for the UI.

        MUST be a pure read — no side effects, idempotent, safe to call any time.
        Derived from params only (the result does not change over the run). The
        registry calls this once at create time and stamps the serialized result
        on JobRecord.properties. Returns an instance of the worker's
        `properties_model`, or None when there is nothing to publish (default).
        """
        return None

    async def compute_state(self, params: TParams) -> JobDerivedState | None:
        """Read source-of-truth Kiln entities and return the operation's true state.

        MUST be a pure read — no side effects, idempotent, safe to call any time.
        Return None only when the worker has no backing entity to consult (e.g.
        the NoopJob fixture); the registry then keeps the last believed snapshot.
        Real workers must override this.
        """
        return None

    async def run(self, params: TParams, ctx: JobContext) -> TResult:
        """MUST be idempotent. Covers both first run and resume — the registry
        calls run() again to resume a paused job; the worker re-orients via
        compute_state(), not a handed-in checkpoint.
        """
        raise NotImplementedError
