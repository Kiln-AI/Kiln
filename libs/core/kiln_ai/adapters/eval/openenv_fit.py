"""Whether a run config can run a grounded eval's cases: the eval's cases were grounded in one
OpenEnv server, and only a run config that lists that server's tools runs them in it."""

from dataclasses import dataclass
from typing import Literal

from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.eval import Eval
from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.tool_id import (
    OPENENV_TOOL_ID_PREFIX,
    openenv_and_tool_name_from_id,
)

OpenEnvMisfit = Literal["no_openenv_tools", "other_openenv_server"]
"""Why a run config doesn't fit a grounded eval (see `openenv_misfit`)."""


def run_config_tool_ids(run_config: TaskRunConfig) -> list[str]:
    """The tool ids a run config lists directly. A run config without a tools config (an
    MCP-type run config) lists none."""
    tools_config = getattr(run_config.run_config_properties, "tools_config", None)
    return list(tools_config.tools) if tools_config is not None else []


def openenv_tool_ids(run_config: TaskRunConfig) -> list[str]:
    return [
        t
        for t in run_config_tool_ids(run_config)
        if t.startswith(OPENENV_TOOL_ID_PREFIX)
    ]


def openenv_misfit(
    eval_openenv_server_id: ID_TYPE | None, run_config: TaskRunConfig
) -> OpenEnvMisfit | None:
    """Why the run config can't run the cases of an eval grounded in `eval_openenv_server_id`,
    or None when it can or the eval isn't grounded. It fits when it lists at least one OpenEnv
    tool and every OpenEnv tool it lists is served by the eval's server. Only the tools the run
    config lists directly count, as in the eval runner."""
    if eval_openenv_server_id is None:
        return None
    tool_ids = openenv_tool_ids(run_config)
    if not tool_ids:
        return "no_openenv_tools"
    if any(
        openenv_and_tool_name_from_id(t)[0] != eval_openenv_server_id for t in tool_ids
    ):
        return "other_openenv_server"
    return None


def openenv_misfit_message(
    misfit: OpenEnvMisfit, run_config_name: str, openenv_server_label: str
) -> str:
    """One sentence for a user: where the eval's cases run, and what the run config lacks."""
    lacks = (
        "has none of its tools"
        if misfit == "no_openenv_tools"
        else "uses tools from another OpenEnv server"
    )
    return (
        f"This eval's cases run in OpenEnv server '{openenv_server_label}'; "
        f"run config '{run_config_name}' {lacks}."
    )


def openenv_server_label(openenv_server_id: str, project: Project | None) -> str:
    """The server's name, or its id when it can't be loaded (deleted, or no project)."""
    openenv_server = (
        OpenEnvServer.from_id_and_parent_path(openenv_server_id, project.path)
        if project is not None and project.path is not None
        else None
    )
    return openenv_server.name if openenv_server is not None else openenv_server_id


@dataclass(frozen=True)
class SkippedRunConfig:
    """A run config left out of a run because it doesn't fit the eval's OpenEnv server."""

    id: str
    name: str
    reason: str


def split_run_configs_by_openenv_fit(
    eval: Eval, run_configs: list[TaskRunConfig], openenv_server_label: str
) -> tuple[list[TaskRunConfig], list[SkippedRunConfig]]:
    """The run configs that fit the eval, in order, and the ones that don't with their
    reasons. Every run config fits an eval that isn't grounded."""
    fitting: list[TaskRunConfig] = []
    skipped: list[SkippedRunConfig] = []
    for run_config in run_configs:
        misfit = openenv_misfit(eval.openenv_server_id, run_config)
        if misfit is None:
            fitting.append(run_config)
        else:
            skipped.append(
                SkippedRunConfig(
                    id=str(run_config.id),
                    name=run_config.name,
                    reason=openenv_misfit_message(
                        misfit, run_config.name, openenv_server_label
                    ),
                )
            )
    return fitting, skipped
