"""Grounding an Eval Builder batch's planned cases in the OpenEnv server its run config
uses, as the frames the builder's grounding stream sends."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncGenerator, Sequence

from kiln_ai.adapters.retry_classification import unwrap_kiln_run_error
from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import Task
from kiln_ai.eval_grounding.batch import (
    CaseGrounded,
    GroundingCaseError,
    GroundingFinished,
    ground_cases,
)
from kiln_ai.eval_grounding.judge_guidance import render_judge_guidance
from kiln_ai.eval_grounding.models import EvalContext, GroundingCase
from kiln_ai.openenv.session_manager import OpenEnvError, OpenEnvSessionManager
from kiln_ai.tools.base_tool import ToolCallDefinition
from kiln_ai.tools.mcp_session_manager import mcp_session_scope
from kiln_ai.tools.openenv_reach import OpenEnvReachError, single_openenv_server_id
from kiln_ai.tools.run_config_tools import tool_definitions_without_episode

from app.desktop.studio_server.api_models.eval_builder_models import (
    CaseDroppedEvent,
    CaseGroundedEvent,
    GroundCaseApi,
    GroundingFailedEvent,
    GroundingFinishedEvent,
    GroundingModelApi,
    GroundingStartedEvent,
)

logger = logging.getLogger(__name__)

GroundingFrame = (
    GroundingStartedEvent
    | CaseGroundedEvent
    | CaseDroppedEvent
    | GroundingFinishedEvent
    | GroundingFailedEvent
)


class NoGroundingServerError(ValueError):
    """The run config's tools reach no OpenEnv server, several, or one the project
    doesn't have, so its cases can't be grounded."""


def grounding_server(
    project: Project, run_config: KilnAgentRunConfigProperties
) -> OpenEnvServer:
    """The one OpenEnv server the run config's tools reach. Raises
    NoGroundingServerError otherwise."""
    try:
        openenv_server_id = single_openenv_server_id(project, _tool_ids(run_config))
    except OpenEnvReachError as e:
        raise NoGroundingServerError(e.message) from e
    if openenv_server_id is None:
        raise NoGroundingServerError(
            "The run config's tools don't use an OpenEnv server, so there is no "
            "environment to check cases against."
        )
    openenv_server = OpenEnvServer.from_id_and_parent_path(
        openenv_server_id, project.path
    )
    if openenv_server is None:
        raise NoGroundingServerError(
            f"OpenEnv server {openenv_server_id} wasn't found."
        )
    return openenv_server


async def grounding_frames(
    *,
    task: Task,
    run_config: KilnAgentRunConfigProperties,
    openenv_server: OpenEnvServer,
    session_manager: OpenEnvSessionManager,
    model: GroundingModelApi,
    specification: str,
    synthetic_user_guide: str | None,
    cases: Sequence[GroundCaseApi],
) -> AsyncGenerator[GroundingFrame, None]:
    """Ground every case, one frame per finished case, between grounding_started and
    grounding_finished. An error that isn't a case's fault ends the frames with
    grounding_failed instead. Closing the iterator early cancels the cases still
    running, and each ends its episode."""
    yield GroundingStartedEvent(total=len(cases))
    try:
        target_tools = await _target_tools(task, run_config, session_manager)
        progress = ground_cases(
            [
                GroundingCase(
                    scenario=case.scenario,
                    seed_prompt=case.seed_prompt,
                    synthetic_user_info=case.synthetic_user_info,
                )
                for case in cases
            ],
            eval_context=EvalContext(
                specification=specification,
                target_task_prompt=task.instruction,
                data_guide=synthetic_user_guide or None,
            ),
            openenv_server=openenv_server,
            session_manager=session_manager,
            model_name=model.model_name,
            model_provider=model.model_provider,
            thinking_level=model.thinking_level,
            target_tools=target_tools,
        )
        async with contextlib.aclosing(progress):
            async for item in progress:
                if isinstance(item, GroundingFinished):
                    yield GroundingFinishedEvent(
                        grounded=item.grounded,
                        dropped=item.dropped,
                        usage=item.usage,
                        usage_complete=item.usage_complete,
                    )
                else:
                    yield _case_frame(item, cases)
    except Exception as e:
        logger.exception("Grounding eval builder cases failed")
        yield _failure_frame(e, openenv_server)


async def _target_tools(
    task: Task,
    run_config: KilnAgentRunConfigProperties,
    session_manager: OpenEnvSessionManager,
) -> list[ToolCallDefinition]:
    async with mcp_session_scope():
        return await tool_definitions_without_episode(
            task, _tool_ids(run_config), session_manager
        )


def _tool_ids(run_config: KilnAgentRunConfigProperties) -> list[str]:
    tools_config = run_config.tools_config
    return list(tools_config.tools) if tools_config is not None else []


def _case_frame(
    item: CaseGrounded, cases: Sequence[GroundCaseApi]
) -> CaseGroundedEvent | CaseDroppedEvent:
    scenario_index = cases[item.case_index].scenario_index
    outcome = item.outcome
    if outcome.status == "dropped":
        if outcome.drop_reason is None or outcome.drop_detail is None:
            raise ValueError("A dropped case has no drop reason or detail.")
        return CaseDroppedEvent(
            case_index=item.case_index,
            scenario_index=scenario_index,
            drop_reason=outcome.drop_reason,
            drop_detail=outcome.drop_detail,
        )
    if (
        outcome.openenv_reset is None
        or outcome.seed_prompt is None
        or outcome.synthetic_user_info is None
        or outcome.reference is None
    ):
        raise ValueError("A grounded case is missing its reset, user or reference.")
    return CaseGroundedEvent(
        case_index=item.case_index,
        scenario_index=scenario_index,
        openenv_reset=outcome.openenv_reset,
        seed_prompt=outcome.seed_prompt,
        synthetic_user_info=outcome.synthetic_user_info,
        judge_guidance=render_judge_guidance(outcome.reference),
    )


def _failure_frame(
    error: Exception, openenv_server: OpenEnvServer
) -> GroundingFailedEvent:
    cause = error.error if isinstance(error, GroundingCaseError) else error
    if isinstance(cause, OpenEnvError):
        return GroundingFailedEvent(
            code="openenv_unreachable",
            message=f"Couldn't use the OpenEnv server at {openenv_server.url}: {cause}",
        )
    root = unwrap_kiln_run_error(cause)
    return GroundingFailedEvent(
        code="grounding_error"
        if isinstance(error, GroundingCaseError)
        else "internal_error",
        message=f"{type(root).__name__}: {root}",
    )
