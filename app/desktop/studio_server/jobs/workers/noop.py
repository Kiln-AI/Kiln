from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from ..models import JobContext, JobDerivedState, JobWorker


class NoopJobParams(BaseModel):
    steps: int = Field(default=10, description="Number of steps to simulate.")
    sleep_per_step_seconds: float = Field(
        default=0.5, description="Seconds to sleep between each simulated step."
    )
    fail_at_step: int | None = Field(
        default=None,
        description="Step index at which to raise a fatal error, failing the whole job. "
        "Null to never fail.",
    )
    error_at_steps: list[int] = Field(
        default=[],
        description="Step indices at which to report a non-fatal per-item error without "
        "stopping the run.",
    )


class NoopJobResult(BaseModel):
    completed_steps: int = Field(
        description="Total number of steps processed (successes plus non-fatal errors)."
    )


class NoopJobWorker(JobWorker[NoopJobParams, NoopJobResult]):
    type_name = "noop"
    params_model = NoopJobParams
    result_model = NoopJobResult
    supports_pause = True

    async def compute_state(self, params: NoopJobParams) -> JobDerivedState | None:
        return None

    async def run(self, params: NoopJobParams, ctx: JobContext) -> NoopJobResult:
        success = error = 0
        for i in range(params.steps):
            await asyncio.sleep(params.sleep_per_step_seconds)
            if params.fail_at_step == i:
                raise RuntimeError(f"intentional fail at step {i}")
            if i in params.error_at_steps:
                error += 1
                await ctx.report_error(f"intentional error at step {i}", step=i)
            else:
                success += 1
            await ctx.report_progress(
                success=success,
                error=error,
                total=params.steps,
                message=f"step {i + 1}/{params.steps}",
            )
        return NoopJobResult(completed_steps=success + error)
