"""FastAPI routes for multi-turn synthetic data generation.

Two routes wrap the runner so the web UI can drive it without a
Python REPL:

  POST /api/projects/{project_id}/tasks/{task_id}/multiturn_sdg/generate_cases
       Synchronous JSON. Calls kiln_server `/generate` via the local
       SyntheticUserClient and returns the N cases as the SDK shape
       (`{seed_prompt, synthetic_user_info: <tagged blob>}` per case).

  POST /api/projects/{project_id}/tasks/{task_id}/multiturn_sdg/run_cases_batch
       SSE stream. Takes (possibly edited) cases + run config + SU driver
       config, runs the drive loop concurrently across cases, and emits
       BatchEvent frames as `data:` lines. Terminator is
       `data: complete\\n\\n`, matching the eval_api SSE convention.

Both routes guard `task.turn_mode == TurnMode.multiturn` before doing any
upstream work — the runner depends on multi-turn TaskRun chaining
(parent_task_run_id is rejected on single-turn tasks).

The kiln_server API key is read server-side (`get_copilot_api_key`) and
never crosses to the browser, matching the copilot pattern. The SU
driver model is exposed to the caller because the choice of model
affects probe quality and cost — deliberate, not internal.
"""

import asyncio
import dataclasses
import json
import logging
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredOutputMode,
    TurnMode,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.usage import MessageUsage
from kiln_ai.synthetic_user.case import SyntheticUserCase as RunnerCase
from kiln_ai.synthetic_user.models import SyntheticUserDriverConfig
from kiln_ai.synthetic_user.runner import (
    CONCURRENCY,
    MAX_TURNS_DEFAULT,
    NUM_CASES_MAX,
    BatchCompletedEvent,
    BatchEvent,
    BatchStartedEvent,
    CaseCompletedEvent,
    CaseFailedEvent,
    TurnCompletedEvent,
    run_cases_batch,
)
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_server.git_sync_decorators import build_save_context, no_write_lock
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import agent_policy_require_approval
from pydantic import BaseModel, Field, model_validator

from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    SyntheticUserCase as SdkSyntheticUserCase,
)
from app.desktop.studio_server.synthetic_user.client import (
    SyntheticUserClient,
    SyntheticUserRequestError,
    SyntheticUserServerError,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key

logger = logging.getLogger(__name__)


# ───────────────────────── Pydantic API models ─────────────────────────

# Cases ride the wire as `list[dict[str, Any]]`: the kiln_server SDK
# emits cases as attrs models with `to_dict()` (used by `/generate_cases`
# below) and the libs/core runner consumes `SyntheticUserCase` (Pydantic).
# Both are field-identical; this route validates dicts straight into the
# libs/core type via Pydantic. Trade-off: TS bindings type cases as
# `Record<string, unknown>` instead of getting per-field autocomplete.
SyntheticUserCaseDict = dict[str, Any]
_CASE_DICT_DESCRIPTION = (
    "A SyntheticUserCase. Shape: {seed_prompt: str, synthetic_user_info: str}. "
    "The synthetic_user_info value is an XML-tagged blob: "
    "<persona>...</persona><goal>...</goal><behavior_guidance>...</behavior_guidance>. "
    "Parsed client-side by kiln_ai.synthetic_user.parser."
)


class GenerateCasesApiInput(BaseModel):
    target_specification: str = Field(..., min_length=1)
    num_cases: int = Field(..., ge=1, le=NUM_CASES_MAX)
    case_prompts: list[str] | None = Field(
        default=None,
        description=(
            "Optional per-case scenario prompts (e.g. from an approved batch "
            "plan). When provided, one case is generated per prompt — case i "
            "is designed around prompt i — instead of leaving case design to "
            "the upstream generator. Length must equal num_cases."
        ),
    )

    @model_validator(mode="after")
    def _case_prompts_match_num_cases(self) -> "GenerateCasesApiInput":
        if self.case_prompts is not None:
            if len(self.case_prompts) != self.num_cases:
                raise ValueError(
                    "case_prompts length must equal num_cases "
                    f"({len(self.case_prompts)} != {self.num_cases})."
                )
            if any(not p.strip() for p in self.case_prompts):
                raise ValueError("case_prompts entries must be non-empty.")
        return self


class GenerateCasesApiOutput(BaseModel):
    cases: list[SyntheticUserCaseDict] = Field(..., description=_CASE_DICT_DESCRIPTION)


class TargetRunConfigSpec(BaseModel):
    """How to invoke the target task on each turn — same fields a manual
    UI run would use.
    """

    model_name: str = Field(..., min_length=1)
    model_provider: ModelProviderName
    prompt_id: str = Field(default="simple_prompt_builder", min_length=1)


class SyntheticUserDriverSpec(BaseModel):
    """How to drive the synthetic user. Caller controls because probe
    quality and cost both depend on the model.
    """

    model_name: str = Field(..., min_length=1)
    model_provider: ModelProviderName


class RunCasesBatchApiInput(BaseModel):
    cases: list[SyntheticUserCaseDict] = Field(
        ...,
        min_length=1,
        max_length=NUM_CASES_MAX,
        description=(
            f"Cases as returned by /generate_cases, optionally edited. "
            f"{_CASE_DICT_DESCRIPTION}"
        ),
    )
    turns: int = Field(
        default=MAX_TURNS_DEFAULT,
        ge=1,
        le=20,
        description=(
            "Exact number of assistant turns to produce per case. The drive "
            "loop has no early termination."
        ),
    )
    target_run_config: TargetRunConfigSpec
    su_driver: SyntheticUserDriverSpec
    batch_tag: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_-]+$",
        min_length=1,
        max_length=64,
        description=(
            "Optional user-supplied batch label. Constrained to "
            "[A-Za-z0-9_-]{1,64} so it can safely be used as a tag on leaf "
            "TaskRuns. Auto-generated if not provided."
        ),
    )


# ───────────────────────── helpers ─────────────────────────

# Concurrent upstream /generate calls when fanning out per-case prompts.
# Mirrors the eval_builder review pipeline's REVIEW_CONCURRENCY.
CASE_GEN_CONCURRENCY = 5


def _case_target_specification(target_specification: str, case_prompt: str) -> str:
    """Append the plan prompt to the shared spec as a scenario constraint —
    the upstream generator has no per-case field, and this avoids adding one.
    """
    return (
        f"{target_specification}\n\n"
        "<case_scenario>\n"
        f"{case_prompt}\n"
        "</case_scenario>\n"
        "Design this single case around the scenario above."
    )


async def _generate_cases_from_prompts(
    client: SyntheticUserClient,
    target_task_prompt: str,
    target_specification: str,
    case_prompts: list[str],
) -> list[SdkSyntheticUserCase]:
    """One upstream single-case call per prompt, concurrency-capped and order
    preserving (case i ← prompt i), so an approved plan maps 1:1 onto cases.
    Any failure fails the whole request; the caller retries from the plan.
    """
    semaphore = asyncio.Semaphore(CASE_GEN_CONCURRENCY)

    async def one(case_prompt: str) -> SdkSyntheticUserCase:
        async with semaphore:
            cases = await client.generate(
                target_task_prompt=target_task_prompt,
                target_specification=_case_target_specification(
                    target_specification, case_prompt
                ),
                num_cases=1,
            )
            if not cases:
                # Upstream 200 with zero cases — keep it on the typed error
                # path rather than crashing on cases[0].
                raise SyntheticUserServerError(
                    code="upstream_invalid_output",
                    message="Synthetic-user generator returned no case for a plan prompt.",
                    status_code=502,
                )
            return cases[0]

    # Not gather(): on first failure we cancel the in-flight siblings so
    # abandoned upstream LLM calls stop spending, then re-raise.
    tasks = [asyncio.ensure_future(one(p)) for p in case_prompts]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        failed = next((t for t in tasks if t.done() and t.exception()), None)
        if failed is not None:
            raise failed.exception()  # type: ignore[misc] # narrowed by the check above
        return [t.result() for t in tasks]
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _guard_multiturn(task: Task) -> None:
    """Reject early if the caller pointed us at a single-turn task. The
    runner's chained TaskRun shape (parent_task_run_id) is rejected on
    single-turn tasks by the datamodel validator — better to surface a
    clean 400 here than a mid-stream chain corruption.
    """
    if task.turn_mode != TurnMode.multiturn:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "task_not_multiturn",
                "message": (
                    "Multi-turn synthetic data generation requires a task with "
                    "turn_mode=multiturn."
                ),
            },
        )


def _to_target_run_config(spec: TargetRunConfigSpec) -> KilnAgentRunConfigProperties:
    return KilnAgentRunConfigProperties(
        model_name=spec.model_name,
        model_provider_name=spec.model_provider,
        prompt_id=spec.prompt_id,
        structured_output_mode=StructuredOutputMode.default,
        tools_config=ToolsRunConfig(tools=[]),
    )


def _to_su_driver_config(spec: SyntheticUserDriverSpec) -> SyntheticUserDriverConfig:
    return SyntheticUserDriverConfig(
        model_name=spec.model_name,
        model_provider_name=spec.model_provider,
    )


# Maps each event dataclass to the snake_case `event` discriminator on the
# SSE frame. Keeps the wire shape stable even if the dataclass types are
# renamed later.
_EVENT_NAMES: dict[type, str] = {
    BatchStartedEvent: "batch_started",
    TurnCompletedEvent: "turn_completed",
    CaseCompletedEvent: "case_completed",
    CaseFailedEvent: "case_failed",
    BatchCompletedEvent: "batch_completed",
}


def _event_to_payload(event: BatchEvent) -> dict:
    name = _EVENT_NAMES.get(type(event))
    if name is None:
        # New dataclass added without registering it — fail loud rather
        # than silently swallowing.
        raise RuntimeError(f"Unregistered BatchEvent type: {type(event).__name__}")
    return {"event": name, **dataclasses.asdict(event)}


def _jsonable(obj: Any) -> Any:
    """json.dumps `default` handler. SSE trace frames embed `MessageUsage`
    (Pydantic) on assistant turns, which doesn't survive `dataclasses.asdict`
    recursion. The whitelist is intentionally narrow: any new Pydantic type
    on the wire must be added here explicitly, prompting a review for
    whether `model_dump()` exposes sensitive fields. Do NOT broaden to
    `hasattr(obj, "model_dump")` or `str(obj)` — silent leakage is worse
    than a loud TypeError that fails the stream.
    """
    if isinstance(obj, MessageUsage):
        return obj.model_dump()
    raise TypeError(f"{type(obj).__name__} is not JSON serializable")


def _to_http_exception(
    exc: SyntheticUserRequestError | SyntheticUserServerError,
) -> HTTPException:
    """Translate SyntheticUserClient's typed exceptions to HTTPExceptions.

    Returns the exception rather than raising so callers can `raise … from exc`
    at the call site — gives the type checker NoReturn semantics for free
    and avoids any chance of unbound-variable bugs after the try block.

    Status preservation: upstream's HTTP status is passed through faithfully
    when it's one of the 4xx/5xx codes the SDK models (401, 422, 500, 502).
    Collapsing a 401 to 400 hides whether the operator's stored API key is
    bad vs the caller's body being malformed — both knowable distinctions
    that the consumer needs to act on.
    """
    if isinstance(exc, SyntheticUserRequestError):
        # 401 (kiln_server auth failed) and 422 (runner sent a bad body)
        # are both client-class errors but distinct causes; preserve.
        status = exc.status_code if exc.status_code in (401, 422) else 400
        return HTTPException(
            status_code=status,
            detail={"code": exc.code, "message": exc.message},
        )
    # SyntheticUserServerError: preserve the upstream 5xx (502 → 502,
    # 503 → 503, ...). Anything unrecognized falls to a clean 500.
    status = (
        exc.status_code if exc.status_code and 500 <= exc.status_code < 600 else 500
    )
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": exc.message},
    )


# ───────────────────────── route registration ─────────────────────────


def connect_multiturn_sdg_api(app: FastAPI) -> None:
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/multiturn_sdg/generate_cases",
        tags=["Multiturn SDG"],
        summary="Generate Multi-Turn SU Cases",
        openapi_extra=agent_policy_require_approval(
            "Generate synthetic-user cases? Uses an LLM call (cost)."
        ),
    )
    async def generate_cases(
        project_id: Annotated[
            str, Path(description="ID of the project containing the target task.")
        ],
        task_id: Annotated[
            str,
            Path(
                description=("ID of the target task. Must be a multi-turn task."),
            ),
        ],
        input: GenerateCasesApiInput,
    ) -> GenerateCasesApiOutput:
        task = task_from_id(project_id, task_id)
        _guard_multiturn(task)

        api_key = get_copilot_api_key()
        client = SyntheticUserClient(api_key=api_key)

        try:
            if input.case_prompts is not None:
                sdk_cases = await _generate_cases_from_prompts(
                    client=client,
                    target_task_prompt=task.instruction,
                    target_specification=input.target_specification,
                    case_prompts=input.case_prompts,
                )
            else:
                sdk_cases = await client.generate(
                    target_task_prompt=task.instruction,
                    target_specification=input.target_specification,
                    num_cases=input.num_cases,
                )
        except (SyntheticUserRequestError, SyntheticUserServerError) as exc:
            raise _to_http_exception(exc) from exc

        return GenerateCasesApiOutput(cases=[c.to_dict() for c in sdk_cases])

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/multiturn_sdg/run_cases_batch",
        tags=["Multiturn SDG"],
        summary="Run Multi-Turn SU Cases Batch",
        openapi_extra=agent_policy_require_approval(
            "Run a multi-turn synthetic-user batch? Invokes the target model "
            "and the SU driver model for several turns per case (cost)."
        ),
    )
    @no_write_lock
    async def stream_run_cases_batch(
        request: Request,
        project_id: Annotated[
            str, Path(description="ID of the project containing the target task.")
        ],
        task_id: Annotated[
            str,
            Path(
                description=("ID of the target task. Must be a multi-turn task."),
            ),
        ],
        input: RunCasesBatchApiInput,
    ) -> StreamingResponse:
        # Guard + decode happen before the stream opens so the client sees
        # a clean 400 / 422 rather than a half-open text/event-stream on
        # bad input.
        task = task_from_id(project_id, task_id)
        _guard_multiturn(task)

        # Parse dict → libs/core RunnerCase. Pydantic raises ValidationError
        # on missing keys or empty strings; surface as a clean 400 instead
        # of letting it explode inside the SSE generator. We go straight to
        # the libs/core type (skipping the SDK round-trip) because the two
        # shapes are field-identical and the runner only needs the libs/core
        # one.
        try:
            runner_cases = [RunnerCase.model_validate(c) for c in input.cases]
        except Exception as exc:  # noqa: BLE001 — Pydantic ValidationError + any future shape drift
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "invalid_case_shape",
                    "message": f"Could not parse cases against the runner shape: {exc}",
                },
            ) from exc

        target_run_config = _to_target_run_config(input.target_run_config)
        su_driver_config = _to_su_driver_config(input.su_driver)
        save_context = build_save_context(request)

        async def event_generator():
            try:
                async for event in run_cases_batch(
                    cases=runner_cases,
                    target_task=task,
                    target_run_config=target_run_config,
                    su_driver_config=su_driver_config,
                    turns=input.turns,
                    concurrency=CONCURRENCY,
                    batch_tag=input.batch_tag,
                    save_context=save_context,
                ):
                    yield (
                        "data: "
                        + json.dumps(
                            _event_to_payload(event),
                            default=_jsonable,
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )
            except Exception as e:  # noqa: BLE001 — last-resort surface
                # The catch is narrow in practice: run_cases_batch
                # swallows per-case failures into CaseFailedEvent, so the
                # only paths that escape here are developer bugs
                # (RuntimeError from _event_to_payload, TypeError from
                # _jsonable). asyncio.CancelledError is BaseException and
                # bypasses this except — correct, since cancellation
                # means the consumer is gone.
                logger.exception("multiturn_sdg run_cases_batch failed mid-stream")
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "event": "batch_failed",
                            # Stable wire code; class name goes in message
                            # so it stays useful for debug without leaking
                            # internal type names onto the wire contract.
                            "error_code": "internal_error",
                            "message": f"{type(e).__name__}: {e}",
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
            yield "data: complete\n\n"

        return CancellableStreamingResponse(
            content=event_generator(),
            media_type="text/event-stream",
        )
