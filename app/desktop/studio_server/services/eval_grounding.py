"""Grounding an Eval Builder batch's planned cases in the OpenEnv server its run config
uses, as the frames the builder's grounding stream sends."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from typing import Any

from kiln_ai.adapters.retry_classification import unwrap_kiln_run_error
from kiln_ai.datamodel.datamodel_enums import TurnMode
from kiln_ai.datamodel.openenv import OpenEnvEpisode, OpenEnvServer
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
from kiln_ai.eval_grounding.models import (
    EvalContext,
    GroundingCase,
    GroundingOutcome,
)
from kiln_ai.openenv.session_manager import OpenEnvError, OpenEnvSessionManager
from kiln_ai.tools.base_tool import ToolCallDefinition
from kiln_ai.tools.mcp_session_manager import mcp_session_scope
from kiln_ai.tools.openenv_reach import OpenEnvReachError, single_openenv_server_id
from kiln_ai.tools.run_config_tools import tool_definitions_without_episode
from kiln_ai.utils.usage import Usage

from app.desktop.studio_server.api_models.eval_builder_models import (
    CaseDroppedEvent,
    CaseGroundedEvent,
    GroundCaseApi,
    GroundingFailedEvent,
    GroundingFinishedEvent,
    GroundingModelApi,
    GroundingStartedEvent,
)
from app.desktop.studio_server.utils.eval_builder_utils import JudgeVerdict

logger = logging.getLogger(__name__)

GroundingFrame = (
    GroundingStartedEvent
    | CaseGroundedEvent
    | CaseDroppedEvent
    | GroundingFinishedEvent
    | GroundingFailedEvent
)


RehearsalJudge = Callable[
    [list[dict[str, Any]], str, OpenEnvEpisode], Awaitable[JudgeVerdict]
]
"""Grades one rehearsal trace with the eval's judge, given the case's judge guidance and
the episode the rehearsal ran in."""

REHEARSAL_JUDGE_TIMEOUT_S = 300.0
"""How long one rehearsal's judgment may take, retries included."""


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


def check_grounded_servers(
    project: Project,
    run_config: KilnAgentRunConfigProperties,
    openenv_server_ids: Sequence[str],
) -> None:
    """Check that every grounded input names the one OpenEnv server the run config's
    tools reach. Raises NoGroundingServerError otherwise: an input run on another
    server would start an episode its tools never touch."""
    server = grounding_server(project, run_config)
    for position, server_id in enumerate(openenv_server_ids):
        if server_id != server.id:
            raise NoGroundingServerError(
                f"Input {position} is grounded in OpenEnv server {server_id}, but "
                f"the run config's tools reach OpenEnv server {server.id}."
            )


async def grounding_frames(
    *,
    task: Task,
    run_config: KilnAgentRunConfigProperties,
    openenv_server: OpenEnvServer,
    session_manager: OpenEnvSessionManager,
    model: GroundingModelApi,
    specification: str,
    data_guide: str | None,
    example_input: str | None,
    cases: Sequence[GroundCaseApi],
    max_turns: int | None = None,
    rehearsal_judge: RehearsalJudge | None = None,
) -> AsyncGenerator[GroundingFrame, None]:
    """Ground every case, one frame per finished case, between grounding_started and
    grounding_finished. A single-turn task grounds in single-turn mode: the agent
    writes each input, matching the task's input schema when it has one. An error that
    isn't a case's fault ends the frames with grounding_failed instead. Closing the
    iterator early cancels the cases still running, and each ends its episode.

    With `rehearsal_judge`, the agent is asked to rehearse each case in a last, clean
    episode, and each grounded case's rehearsal is judged before its frame is sent, and
    the frame carries the verdict. Without it, grounding asks for no rehearsal. A judgment that fails or times out
    leaves the case unjudged, never failed."""
    single_turn = task.turn_mode != TurnMode.multiturn
    judging = _RehearsalJudging(rehearsal_judge) if rehearsal_judge else None
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
                data_guide=data_guide or None,
                mode="single_turn" if single_turn else "multi_turn",
                input_schema=task.input_json_schema if single_turn else None,
                example_input=(example_input or None) if single_turn else None,
                max_turns=None if single_turn else max_turns,
                rehearse=rehearsal_judge is not None,
            ),
            openenv_server=openenv_server,
            session_manager=session_manager,
            model_name=model.model_name,
            model_provider=model.model_provider,
            thinking_level=model.thinking_level,
            target_tools=target_tools,
            on_grounded=judging.judge if judging else None,
        )
        async with contextlib.aclosing(progress):
            async for item in progress:
                if isinstance(item, GroundingFinished):
                    yield GroundingFinishedEvent(
                        grounded=item.grounded,
                        dropped=item.dropped,
                        usage=item.usage,
                        usage_complete=item.usage_complete,
                        rehearsal_judge_usage=judging.usage if judging else None,
                    )
                else:
                    yield _case_frame(
                        item,
                        cases,
                        judging.verdicts.get(item.case_index) if judging else None,
                    )
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


class _RehearsalJudging:
    """One grounding run's rehearsal judgments: the verdict per case, by position, and
    what they cost."""

    def __init__(self, judge: RehearsalJudge) -> None:
        self._judge = judge
        self.verdicts: dict[int, JudgeVerdict] = {}
        self.usage: Usage | None = None

    async def judge(self, case_index: int, outcome: GroundingOutcome) -> None:
        """Judge the case's rehearsal, when it has one. Never raises: a failed judgment
        leaves the case without a verdict."""
        if (
            outcome.rehearsal_trace is None
            or outcome.rehearsal_episode is None
            or outcome.reference is None
        ):
            return
        try:
            verdict = await asyncio.wait_for(
                self._judge(
                    outcome.rehearsal_trace,
                    render_judge_guidance(outcome.reference),
                    outcome.rehearsal_episode,
                ),
                timeout=REHEARSAL_JUDGE_TIMEOUT_S,
            )
        except Exception:
            logger.warning(
                "Judging the rehearsal of grounding case %d failed",
                case_index,
                exc_info=True,
            )
            return
        self.verdicts[case_index] = verdict
        if verdict.usage is not None:
            self.usage = (
                verdict.usage if self.usage is None else self.usage + verdict.usage
            )


def _case_frame(
    item: CaseGrounded,
    cases: Sequence[GroundCaseApi],
    rehearsal: JudgeVerdict | None = None,
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
    if outcome.openenv_reset is None or outcome.reference is None:
        raise ValueError("A grounded case is missing its reset or reference.")
    return CaseGroundedEvent(
        case_index=item.case_index,
        scenario_index=scenario_index,
        openenv_reset=outcome.openenv_reset,
        seed_prompt=outcome.seed_prompt,
        synthetic_user_info=outcome.synthetic_user_info,
        input=outcome.input,
        judge_guidance=render_judge_guidance(outcome.reference),
        rehearsal_score=rehearsal.judge_score if rehearsal else None,
        rehearsal_reasoning=rehearsal.judge_reasoning if rehearsal else None,
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
