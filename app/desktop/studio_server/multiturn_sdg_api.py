"""FastAPI route for multi-turn synthetic data generation, plus the drive
request models and helpers the eval builder's pipelines share.

  POST /api/projects/{project_id}/tasks/{task_id}/multiturn_sdg/generate_cases
       Synchronous JSON. Calls kiln_server `/generate` via the local
       SyntheticUserClient and returns the N cases as the SDK shape
       (`{seed_prompt, synthetic_user_info: <tagged blob>}` per case).

The route and `guard_multiturn` reject single-turn tasks before any upstream
work: the runner the pipelines drive depends on multi-turn TaskRun chaining
(parent_task_run_id is rejected on single-turn tasks).

The kiln_server API key is read server-side (`get_copilot_api_key`) and
never crosses to the browser, matching the copilot pattern. The SU
driver model is exposed to the caller because the choice of model
affects probe quality and cost.
"""

from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    TurnMode,
)
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    RunConfigProperties,
    as_kiln_agent_run_config,
)
from kiln_ai.datamodel.task import Task
from kiln_ai.synthetic_user.models import SyntheticUserDriverConfig
from kiln_ai.synthetic_user.runner import MAX_TURNS_DEFAULT, NUM_CASES_MAX
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import agent_policy_require_approval
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from app.desktop.studio_server.eval_api import task_run_config_from_id
from app.desktop.studio_server.synthetic_user.client import (
    SyntheticUserClient,
    SyntheticUserRequestError,
    SyntheticUserServerError,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key

# ───────────────────────── Pydantic API models ─────────────────────────

# Cases ride the wire as `list[dict[str, Any]]`: the kiln_server SDK
# emits cases as attrs models with `to_dict()` (used by `/generate_cases`
# below) and the libs/core runner consumes `SyntheticUserCase` (Pydantic).
# Both are field-identical; the multi-turn pipeline validates dicts straight
# into the libs/core type via Pydantic. Trade-off: TS bindings type cases as
# `Record<string, unknown>` instead of getting per-field autocomplete.
SyntheticUserCaseDict = dict[str, Any]
_CASE_DICT_DESCRIPTION = (
    "A SyntheticUserCase. Shape: {seed_prompt: str, synthetic_user_info: str, "
    "scenario_index?: int | null}. The synthetic_user_info value is an "
    "XML-tagged blob: "
    "<persona>...</persona><goal>...</goal><behavior_guidance>...</behavior_guidance>. "
    "Parsed client-side by kiln_ai.synthetic_user.parser. scenario_index is "
    "set only on scenario batches (generate_cases with case_prompts) and maps "
    "the case back to its plan prompt."
)


class GenerateCasesApiInput(BaseModel):
    target_specification: str = Field(..., min_length=1)
    num_cases: int = Field(..., ge=1, le=NUM_CASES_MAX)
    case_prompts: list[str] | None = Field(
        default=None,
        description=(
            "Optional per-case scenario prompts (e.g. from an approved batch "
            "plan). When provided, the batch is generated in ONE upstream "
            "call with case i designed around prompt i; each returned case "
            "carries scenario_index. Under the upstream salvage contract a "
            "flaky case is dropped rather than failing the batch, so the "
            "response may hold fewer cases than prompts — scenario_index, "
            "not position, maps a case to its prompt. Length must equal "
            "num_cases."
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


class SyntheticUserDriverSpec(BaseModel):
    """How to drive the synthetic user. Caller controls because probe
    quality and cost both depend on the model.
    """

    model_name: str = Field(..., min_length=1)
    model_provider: ModelProviderName


class TargetRunConfigFields(BaseModel):
    """The target-config half of every drive request — inherited by both the
    multi-turn pipeline request and the single-turn pipeline request,
    so the two drive contracts can't drift."""

    target_run_config: RunConfigProperties | None = Field(
        default=None,
        description=(
            "Inline run config for the target task, used verbatim — the "
            "same full properties shape a manual run sends, tools included. "
            "For driving a config that isn't worth saving (ad-hoc "
            "experiments, scripting). Must be a Kiln agent config. Exactly "
            "one of target_run_config / target_run_config_id is required."
        ),
    )
    target_run_config_id: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "ID of one of the target task's saved run configs. The drive "
            "uses the saved config verbatim — model, prompt, sampling, and "
            "tools — so the agent under test behaves exactly like a manual "
            "run, and driven runs attribute back to the config. Exactly one "
            "of target_run_config / target_run_config_id is required."
        ),
    )

    @model_validator(mode="after")
    def _exactly_one_target_config(self) -> Self:
        if (self.target_run_config is None) == (self.target_run_config_id is None):
            raise ValueError(
                "Provide exactly one of target_run_config or target_run_config_id."
            )
        return self


class RunCasesBatchApiInput(TargetRunConfigFields):
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
        description="Ceiling on the assistant turns produced per case.",
    )
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


def guard_multiturn(task: Task) -> None:
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


def resolve_target_run_config(
    input: TargetRunConfigFields, project_id: str, task_id: str
) -> tuple[KilnAgentRunConfigProperties, str | None]:
    """The drive's target config, from whichever source the request used,
    plus the saved config's id for run attribution (None on the inline
    path — those runs are ad-hoc by definition).

    Both sources carry the FULL run config — tools included — so the driven
    task behaves exactly like a manual run of that config. Raises
    HTTPException, so callers must resolve BEFORE opening an SSE stream
    (clean 4xx, not a mid-stream error frame).
    """
    if input.target_run_config_id is not None:
        # task_run_config_from_id is the same resolver the run-config list
        # endpoint is built on, so every id the UI can offer resolves here —
        # including virtual fine-tune configs, which never appear under
        # task.run_configs().
        try:
            run_config = task_run_config_from_id(
                project_id, task_id, input.target_run_config_id
            )
        except HTTPException as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "run_config_not_found",
                    "message": (
                        "Task has no saved run config with ID "
                        f"'{input.target_run_config_id}'."
                    ),
                },
            ) from exc
        try:
            properties = as_kiln_agent_run_config(run_config.run_config_properties)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "run_config_not_agent",
                    "message": (
                        "Driving the task requires a Kiln agent run config; "
                        "the selected run config is a different type."
                    ),
                },
            ) from exc
        return properties, input.target_run_config_id
    if input.target_run_config is None:
        # Unreachable behind the request validator; a regression there is a
        # server bug, not a client error.
        raise RuntimeError("target_run_config missing despite request validation")
    try:
        return as_kiln_agent_run_config(input.target_run_config), None
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "run_config_not_agent",
                "message": (
                    "Driving the task requires a Kiln agent run config; "
                    "the inline run config is a different type."
                ),
            },
        ) from exc


def to_su_driver_config(spec: SyntheticUserDriverSpec) -> SyntheticUserDriverConfig:
    return SyntheticUserDriverConfig(
        model_name=spec.model_name,
        model_provider_name=spec.model_provider,
    )


def _to_http_exception(
    exc: SyntheticUserRequestError | SyntheticUserServerError,
) -> HTTPException:
    """Translate SyntheticUserClient's typed exceptions to HTTPExceptions.

    Returns the exception rather than raising so callers can `raise … from exc`
    at the call site — gives the type checker NoReturn semantics for free
    and avoids any chance of unbound-variable bugs after the try block.

    Status preservation: upstream's status is passed through faithfully for
    401/422 client errors and for any upstream 5xx; everything else collapses
    to a clean 400/500.
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
        guard_multiturn(task)

        api_key = get_copilot_api_key()
        client = SyntheticUserClient(api_key=api_key)

        try:
            # One upstream call either way. Plan prompts ride as
            # case_scenarios (one batch pass, case i ← prompt i, salvage
            # drops a flaky case instead of failing the batch).
            sdk_cases = await client.generate(
                target_task_prompt=task.instruction,
                target_specification=input.target_specification,
                num_cases=input.num_cases,
                case_scenarios=input.case_prompts,
            )
        except (SyntheticUserRequestError, SyntheticUserServerError) as exc:
            raise _to_http_exception(exc) from exc

        if not sdk_cases:
            # Upstream promises >= 1 case or a 502; an empty 200 is a broken
            # contract. Surface it typed rather than handing the UI an empty
            # batch it would fail on later with no visible cause.
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "upstream_invalid_output",
                    "message": "Synthetic-user generator returned no cases.",
                },
            )
        return GenerateCasesApiOutput(cases=[c.to_dict() for c in sdk_cases])
