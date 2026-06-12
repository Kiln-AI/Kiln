from __future__ import annotations

import asyncio

from kiln_ai.adapters.fine_tune.base_finetune import FineTuneStatus
from kiln_ai.adapters.fine_tune.finetune_registry import finetune_registry
from kiln_ai.datamodel import Finetune, FineTuneStatusType
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from pydantic import BaseModel

from ...finetune_api import finetune_from_id
from ..models import JobContext, JobDerivedState, JobWorker


class FinetuneJobParams(BaseModel):
    project_id: str
    task_id: str
    finetune_id: str


class FinetuneJobResult(BaseModel):
    status: str
    message: str | None = None


class FinetuneStatusUnknownError(RuntimeError):
    """Raised when the finetune's provider can't be resolved to query status.

    Distinct from a provider-reported failure: the local Kiln side can't even
    ask the provider what's going on (deleted Finetune record, missing
    provider name, provider gone from the registry). Bubbles up to the job
    system as a FAILED job so the user sees something rather than a silently
    stalled watcher.
    """


class FinetuneJobFailedError(RuntimeError):
    """Raised when the provider reports the finetune as failed.

    Carries the provider-supplied error_details (if any) as the message so the
    failure surfaces in the jobs panel's error log.
    """


class FinetuneJobWorker(JobWorker[FinetuneJobParams, FinetuneJobResult]):
    """Background watcher for a provider-side finetune run.

    Pure observer: the finetune is already submitted to the provider by the
    create endpoint; this worker just polls FineTuneStatus until terminal. No
    pause/cancel — there's nothing local to interrupt, and the user can't
    usefully abort a remote training from here.
    """

    type_name = "finetune"
    params_model = FinetuneJobParams
    result_model = FinetuneJobResult
    supports_pause = False
    supports_cancel = False

    # Provider-side trainings take minutes to hours. 30s strikes a balance
    # between freshness and avoiding rate-limit pressure on provider APIs.
    POLL_INTERVAL_SECONDS: float = 30.0

    async def compute_state(self, params: FinetuneJobParams) -> JobDerivedState:
        status = await self._fetch_status(params)
        completed = status.status == FineTuneStatusType.completed
        return JobDerivedState(
            total=1,
            success=1 if completed else 0,
            error=0,
            is_complete=status.status
            in (FineTuneStatusType.completed, FineTuneStatusType.failed),
            message=status.message,
        )

    async def run(
        self, params: FinetuneJobParams, ctx: JobContext
    ) -> FinetuneJobResult:
        while True:
            status = await self._fetch_status(params)
            if status.status == FineTuneStatusType.completed:
                await ctx.report_progress(
                    success=1, error=0, total=1, message=status.message
                )
                return FinetuneJobResult(
                    status=status.status.value, message=status.message
                )
            if status.status == FineTuneStatusType.failed:
                raise FinetuneJobFailedError(
                    status.error_details or status.message or "Finetune failed"
                )
            # Non-terminal (pending / running / unknown): report current message
            # for UI freshness and sleep until the next poll. total stays None
            # so the table doesn't render a misleading 0% progress bar.
            await ctx.report_progress(success=0, error=0, message=status.message)
            await asyncio.sleep(self.POLL_INTERVAL_SECONDS)

    async def _fetch_status(self, params: FinetuneJobParams) -> FineTuneStatus:
        finetune = self._load_finetune(params)
        try:
            provider_name = ModelProviderName[finetune.provider]
        except (KeyError, ValueError) as exc:
            raise FinetuneStatusUnknownError(
                f"Provider '{finetune.provider}' is not available for fine-tuning"
            ) from exc
        if provider_name not in finetune_registry:
            raise FinetuneStatusUnknownError(
                f"Provider '{finetune.provider}' is not available for fine-tuning"
            )
        adapter_cls = finetune_registry[provider_name]
        return await adapter_cls(finetune).status()

    def _load_finetune(self, params: FinetuneJobParams) -> Finetune:
        # finetune_from_id raises HTTPException(404) if the record was deleted;
        # let it propagate — the job dies with a FAILED status, which is the
        # right escape hatch once there's nothing left to watch.
        return finetune_from_id(params.project_id, params.task_id, params.finetune_id)
