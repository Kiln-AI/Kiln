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
    error: int = 0
    is_complete: bool = False
    message: str | None = None


class JobError(BaseModel):
    """Small failure summary stamped on the record. Detail lives in the error log."""

    error: str | None = None
    detail: dict[str, Any] | None = None


class JobRecord(BaseModel):
    """Ephemeral, in-memory bookkeeping for a single job. Never persisted to disk."""

    id: str
    # Friendly adjective-noun label assigned by the registry at create time,
    # used in the UI instead of the cryptic `id`. Not unique — `id` remains
    # the canonical key. Optional for backward compatibility with older
    # records that may have been created before this field existed.
    name: str | None = None
    type: str
    status: BackgroundJobStatus
    run_id: str | None = None
    progress: JobProgress = Field(default_factory=JobProgress)
    params: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: JobError | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = None
    supports_pause: bool = False
    # Some workers (e.g. provider-side finetune watchers) wrap external work
    # that the user can't usefully interrupt from the local UI. The cancel
    # button is hidden for those jobs and the registry's cancel() refuses.
    supports_cancel: bool = True
    # Producer-supplied lifecycle identity. When set, creating a new job with
    # the same (type, idempotency_key) tears down any non-terminal predecessor
    # (cancel + remove from the index) so the panel doesn't pile up duplicate
    # rows for the same logical run. The producer picks the granularity — for
    # evals this is (eval, eval_config, run_config); for finetune watchers it's
    # left unset because each provider submission is a fresh identity.
    # Kept distinct from metadata.tag, which is the *display/back-nav* identity
    # — same in most cases today but the contracts are unrelated.
    idempotency_key: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = None
    ended_at: datetime | None = None


ReportProgress = Callable[["JobProgressUpdate"], Awaitable[None]]
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
        report_error: ReportError,
    ) -> None:
        self.job_id = job_id
        self.run_id = run_id
        self._report_progress = report_progress
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
    supports_pause: ClassVar[bool] = False
    # Default True: most workers do in-process work that the user may reasonably
    # want to abort. Set False on workers wrapping external state we shouldn't
    # interrupt locally (e.g. a remote finetune already submitted to a provider).
    supports_cancel: ClassVar[bool] = True

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
