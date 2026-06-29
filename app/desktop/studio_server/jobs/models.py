from __future__ import annotations

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


class JobProgress(BaseModel):
    """Count-based progress for a job.

    Processed = success + error; remaining = total - success - error. The error
    field is a count only — the actual messages live in the per-run error log.
    """

    total: int | None = None
    success: int = 0
    error: int = 0
    message: str | None = None
    updated_at: datetime = Field(default_factory=_utc_now)


class JobDerivedState(BaseModel):
    """A worker's view of the operation's true state, read from source-of-truth entities."""

    total: int | None = None
    success: int = 0
    # None means "not derivable from source-of-truth entities" — failed items
    # leave no entity to count, so the registry keeps the live reported error
    # count instead of clobbering it to 0 (mirrors `total`/`message`).
    error: int | None = None
    is_complete: bool = False
    message: str | None = None


class JobError(BaseModel):
    """Small failure summary stamped on the record. Detail lives in the error log."""

    error: str | None = None
    detail: dict[str, Any] | None = None


class JobRecord(BaseModel):
    """Ephemeral, in-memory bookkeeping for a single job. Never persisted to disk."""

    id: str
    type: str
    status: BackgroundJobStatus
    run_id: str | None = None
    progress: JobProgress = Field(default_factory=JobProgress)
    # Typed, per-worker progress detail (validated against the worker's
    # `progress_model`). The generic `progress` above is the universal counter;
    # this carries the rich per-kind shape a worker needs the UI to render
    # (e.g. RAG's four-phase breakdown). Kept as a dict on the wire so the core
    # stays worker-agnostic; the frontend casts it to the worker's model.
    progress_detail: dict[str, Any] | None = None
    # Static, worker-published descriptive properties for this job (validated
    # against the worker's `properties_model`). Derived once from params at
    # create time; unlike `progress`, it does not change over the run. Kept as a
    # dict on the wire so the core stays worker-agnostic; the frontend casts it
    # to the worker's model.
    properties: dict[str, Any] | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: JobError | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = None
    supports_pause: bool = False
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = None
    ended_at: datetime | None = None


ReportProgress = Callable[["JobProgressUpdate"], Awaitable[None]]
ReportProgressDetail = Callable[[BaseModel], Awaitable[None]]
ReportError = Callable[[str, dict[str, Any]], Awaitable[None]]


class JobProgressUpdate(BaseModel):
    success: int
    error: int = 0
    total: int | None = None
    message: str | None = None


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
    # Optional typed model for static, worker-published descriptive properties
    # returned by describe() and stamped on JobRecord.properties. Leave None for
    # workers that have nothing descriptive to publish.
    properties_model: ClassVar[type[BaseModel] | None] = None
    supports_pause: ClassVar[bool] = False

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
