import asyncio
from datetime import datetime
from typing import Annotated, Any, Callable, Iterable, TypeVar

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.provider_tools import provider_enabled
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.extraction import Kind
from kiln_ai.datamodel.prompt_type import prompt_type_label
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.task_output import DataSourceType
from kiln_ai.utils.formatting import truncate_to_words_with_agent_sentinel
from kiln_server.prompt_api import prompt_generators
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import ALLOW_AGENT
from pydantic import BaseModel

from app.desktop.studio_server.eval_api import get_all_run_configs

# Skill prefix used to split tool_ids into tool_ids and skill_ids
_SKILL_PREFIX = "kiln_tool::skill::"

T = TypeVar("T")


# --- Response Models ---


class AgentOverviewProject(BaseModel):
    id: ID_TYPE
    name: str
    description: str | None


class AgentOverviewTask(BaseModel):
    id: ID_TYPE
    name: str
    description: str | None
    instruction: str
    input_json_schema: Any | None
    output_json_schema: Any | None
    default_run_config_id: ID_TYPE | None


class AgentOverviewDataset(BaseModel):
    total_count: int
    by_tag: dict[str, int]
    by_source: dict[str, int]
    by_rating: dict[str, int]


class AgentOverviewDocs(BaseModel):
    doc_count: int
    by_tag: dict[str, int]
    by_kind: dict[str, int]


class AgentOverviewSearchTool(BaseModel):
    id: ID_TYPE
    name: str
    tool_name: str
    tool_description: str
    description: str | None
    tags: list[str] | None


class AgentOverviewSearchTools(BaseModel):
    items: list[AgentOverviewSearchTool]
    archived_search_tool_count: int


class AgentOverviewPrompt(BaseModel):
    id: str
    name: str
    type: str


class AgentOverviewPrompts(BaseModel):
    total: int
    showing: str
    generators_from_task_instruction_count: int
    items: list[AgentOverviewPrompt]


class AgentOverviewSpec(BaseModel):
    eval_id: ID_TYPE
    name: str
    spec_type: str
    priority: str
    status: str
    tags: list[str]


class AgentOverviewSpecs(BaseModel):
    items: list[AgentOverviewSpec]
    archived_spec_count: int


class AgentOverviewOutputScore(BaseModel):
    name: str
    type: str


class AgentOverviewEval(BaseModel):
    eval_id: ID_TYPE
    name: str
    description: str | None
    template: str | None
    default_judge_config_id: ID_TYPE | None
    output_scores: list[AgentOverviewOutputScore]
    favourite: bool


class AgentOverviewToolServer(BaseModel):
    id: ID_TYPE
    name: str
    type: str
    description: str | None


class AgentOverviewToolServers(BaseModel):
    items: list[AgentOverviewToolServer]
    archived_tool_server_count: int


class AgentOverviewRunConfig(BaseModel):
    id: ID_TYPE
    name: str
    description: str | None
    type: str
    model_name: str | None
    model_provider: str | None
    prompt_id: str | None
    tool_ids: list[str]
    skill_ids: list[str]
    starred: bool


class AgentOverviewRunConfigs(BaseModel):
    default_run_config_id: ID_TYPE | None
    total: int
    showing: str
    items: list[AgentOverviewRunConfig]


class AgentOverviewFineTunes(BaseModel):
    total_count: int


class AgentOverviewPromptOptimizationJobs(BaseModel):
    total_count: int


class AgentOverviewSkill(BaseModel):
    id: ID_TYPE
    name: str
    description: str


class AgentOverviewSkills(BaseModel):
    items: list[AgentOverviewSkill]
    archived_skill_count: int


class AgentOverview(BaseModel):
    project: AgentOverviewProject
    task: AgentOverviewTask
    dataset: AgentOverviewDataset
    docs: AgentOverviewDocs
    search_tools: AgentOverviewSearchTools
    prompts: AgentOverviewPrompts
    specs: AgentOverviewSpecs
    evals: list[AgentOverviewEval]
    tool_servers: AgentOverviewToolServers
    run_configs: AgentOverviewRunConfigs
    fine_tunes: AgentOverviewFineTunes
    prompt_optimization_jobs: AgentOverviewPromptOptimizationJobs
    skills: AgentOverviewSkills
    connected_providers: dict[str, dict[str, Any]]


# --- Helpers ---


def _top_n_by_recency(
    items: Iterable[T],
    *,
    key: Callable[[T], tuple[datetime, str]],
    cap: int,
) -> list[T]:
    return sorted(items, key=key, reverse=True)[:cap]


def _split_tool_and_skill_ids(
    tool_ids: list[str],
) -> tuple[list[str], list[str]]:
    tools: list[str] = []
    skills: list[str] = []
    for tid in tool_ids:
        if tid.startswith(_SKILL_PREFIX):
            skills.append(tid)
        else:
            tools.append(tid)
    return tools, skills


def _dataset_stats(task: Task) -> AgentOverviewDataset:
    by_tag: dict[str, int] = {}
    by_source: dict[str, int] = {src.value: 0 for src in DataSourceType}
    by_rating: dict[str, int] = {str(i): 0 for i in range(1, 6)}
    by_rating["unrated"] = 0
    total = 0

    for run in task.runs(readonly=True):
        total += 1
        for tag in run.tags:
            by_tag[tag] = by_tag.get(tag, 0) + 1

        output = run.repaired_output if run.repaired_output is not None else run.output
        if output.source is not None:
            key = output.source.type.value
            by_source[key] = by_source.get(key, 0) + 1

        if (
            output.rating is not None
            and output.rating.value is not None
            and output.rating.type == TaskOutputRatingType.five_star
        ):
            star = str(int(output.rating.value))
            by_rating[star] = by_rating.get(star, 0) + 1
        else:
            by_rating["unrated"] += 1

    return AgentOverviewDataset(
        total_count=total,
        by_tag=by_tag,
        by_source=by_source,
        by_rating=by_rating,
    )


def _docs_stats(project: Project) -> AgentOverviewDocs:
    by_tag: dict[str, int] = {}
    by_kind: dict[str, int] = {k.value: 0 for k in Kind}
    total = 0

    for doc in project.documents(readonly=True):
        total += 1
        by_kind[doc.kind.value] = by_kind.get(doc.kind.value, 0) + 1
        for tag in doc.tags:
            by_tag[tag] = by_tag.get(tag, 0) + 1

    return AgentOverviewDocs(
        doc_count=total,
        by_tag=by_tag,
        by_kind=by_kind,
    )


def _search_tools_block(project: Project) -> AgentOverviewSearchTools:
    items: list[AgentOverviewSearchTool] = []
    archived_count = 0
    for rc in project.rag_configs(readonly=True):
        if rc.is_archived:
            archived_count += 1
            continue
        items.append(
            AgentOverviewSearchTool(
                id=rc.id,
                name=rc.name,
                tool_name=rc.tool_name,
                tool_description=rc.tool_description,
                description=rc.description,
                tags=rc.tags,
            )
        )
    return AgentOverviewSearchTools(
        items=items, archived_search_tool_count=archived_count
    )


def _tool_servers_block(project: Project) -> AgentOverviewToolServers:
    items: list[AgentOverviewToolServer] = []
    archived_count = 0
    for ts in project.external_tool_servers(readonly=True):
        if ts.properties.get("is_archived", False):
            archived_count += 1
            continue
        items.append(
            AgentOverviewToolServer(
                id=ts.id,
                name=ts.name,
                type=ts.type.value,
                description=ts.description,
            )
        )
    return AgentOverviewToolServers(
        items=items, archived_tool_server_count=archived_count
    )


def _skills_block(project: Project) -> AgentOverviewSkills:
    items: list[AgentOverviewSkill] = []
    archived_count = 0
    for skill in project.skills(readonly=True):
        if skill.is_archived:
            archived_count += 1
            continue
        items.append(
            AgentOverviewSkill(
                id=skill.id,
                name=skill.name,
                description=skill.description,
            )
        )
    return AgentOverviewSkills(items=items, archived_skill_count=archived_count)


def _specs_block(task: Task) -> AgentOverviewSpecs:
    items: list[AgentOverviewSpec] = []
    archived_count = 0
    for spec in task.specs(readonly=True):
        if spec.status.value == "archived":
            archived_count += 1
            continue
        items.append(
            AgentOverviewSpec(
                eval_id=spec.eval_id,
                name=spec.name,
                spec_type=spec.properties.get("spec_type", "unknown"),
                priority=spec.priority.name,
                status=spec.status.value,
                tags=spec.tags,
            )
        )
    return AgentOverviewSpecs(items=items, archived_spec_count=archived_count)


def _evals_block(task: Task) -> list[AgentOverviewEval]:
    result: list[AgentOverviewEval] = []
    for ev in task.evals(readonly=True):
        result.append(
            AgentOverviewEval(
                eval_id=ev.id,
                name=ev.name,
                description=ev.description,
                template=ev.template.value if ev.template else None,
                default_judge_config_id=ev.current_config_id,
                output_scores=[
                    AgentOverviewOutputScore(name=s.name, type=s.type.value)
                    for s in ev.output_scores
                ],
                favourite=ev.favourite,
            )
        )
    return result


def _prompts_block(
    task: Task, project: Project, task_run_configs: list[TaskRunConfig]
) -> AgentOverviewPrompts:
    generators_from_task_instruction_count = len(prompt_generators)

    pool: list[tuple[str, str, str, datetime]] = []

    for prompt in task.prompts(readonly=True):
        prompt_id = f"id::{prompt.id}"
        pool.append(
            (
                prompt_id,
                prompt.name,
                prompt_type_label(prompt_id, prompt.generator_id),
                prompt.created_at,
            )
        )

    for ft in task.finetunes(readonly=True):
        if ft.fine_tune_model_id is not None:
            prompt_id = f"fine_tune_prompt::{project.id}::{task.id}::{ft.id}"
            pool.append(
                (
                    prompt_id,
                    ft.name,
                    prompt_type_label(prompt_id, None),
                    ft.created_at,
                )
            )

    for rc in task_run_configs:
        if rc.prompt is not None:
            prompt_id = f"task_run_config::{project.id}::{task.id}::{rc.id}"
            pool.append(
                (
                    prompt_id,
                    rc.name,
                    prompt_type_label(prompt_id, rc.prompt.generator_id),
                    rc.created_at,
                )
            )

    total = len(pool)
    selected = _top_n_by_recency(pool, key=lambda item: (item[3], item[0]), cap=5)
    items = [AgentOverviewPrompt(id=s[0], name=s[1], type=s[2]) for s in selected]

    return AgentOverviewPrompts(
        total=total,
        showing=f"{len(items)} of {total}",
        generators_from_task_instruction_count=generators_from_task_instruction_count,
        items=items,
    )


def _run_configs_block(
    task: Task, task_run_configs: list[TaskRunConfig]
) -> AgentOverviewRunConfigs:
    total = len(task_run_configs)

    starred: list[TaskRunConfig] = []
    unstarred: list[TaskRunConfig] = []
    for rc in task_run_configs:
        if rc.starred:
            starred.append(rc)
        else:
            unstarred.append(rc)

    sorted_starred = _top_n_by_recency(
        starred,
        key=lambda rc: (rc.created_at, str(rc.id)),
        cap=len(starred),
    )
    sorted_unstarred = _top_n_by_recency(
        unstarred,
        key=lambda rc: (rc.created_at, str(rc.id)),
        cap=max(0, 5 - len(starred)),
    )

    if len(starred) >= 5:
        selected = sorted_starred
    else:
        selected = sorted_starred + sorted_unstarred

    items: list[AgentOverviewRunConfig] = []
    for rc in selected:
        props = rc.run_config_properties
        model_name: str | None = None
        model_provider: str | None = None
        prompt_id: str | None = None
        tool_ids: list[str] = []
        skill_ids: list[str] = []
        rc_type = props.type

        if isinstance(props, KilnAgentRunConfigProperties):
            model_name = props.model_name
            model_provider = props.model_provider_name.value
            prompt_id = props.prompt_id
            if props.tools_config is not None:
                all_ids = list(props.tools_config.tools)
                tool_ids, skill_ids = _split_tool_and_skill_ids(all_ids)

        items.append(
            AgentOverviewRunConfig(
                id=rc.id,
                name=rc.name,
                description=rc.description,
                type=rc_type,
                model_name=model_name,
                model_provider=model_provider,
                prompt_id=prompt_id,
                tool_ids=tool_ids,
                skill_ids=skill_ids,
                starred=rc.starred,
            )
        )

    return AgentOverviewRunConfigs(
        default_run_config_id=task.default_run_config_id,
        total=total,
        showing=f"{len(items)} of {total}",
        items=items,
    )


async def _connected_providers_block() -> dict[str, dict[str, Any]]:
    names = list(ModelProviderName)
    enabled = await asyncio.gather(*(provider_enabled(n) for n in names))
    return {name.value: {} for name, is_on in zip(names, enabled) if is_on}


def _fine_tunes_block(task: Task) -> AgentOverviewFineTunes:
    return AgentOverviewFineTunes(
        total_count=sum(1 for _ in task.finetunes(readonly=True))
    )


def _prompt_optimization_jobs_block(task: Task) -> AgentOverviewPromptOptimizationJobs:
    return AgentOverviewPromptOptimizationJobs(
        total_count=sum(1 for _ in task.prompt_optimization_jobs(readonly=True))
    )


# --- Route ---


def connect_agent_api(app: FastAPI):
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/agent_overview",
        summary="Agent Overview",
        tags=["Agent"],
        openapi_extra=ALLOW_AGENT,
    )
    async def agent_overview(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
    ) -> AgentOverview:
        task = task_from_id(project_id, task_id)
        project = task.parent_project()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        task_run_configs = get_all_run_configs(project_id, task_id)

        instruction_text = truncate_to_words_with_agent_sentinel(task.instruction, 70)

        return AgentOverview(
            project=AgentOverviewProject(
                id=project.id,
                name=project.name,
                description=project.description,
            ),
            task=AgentOverviewTask(
                id=task.id,
                name=task.name,
                description=task.description,
                instruction=instruction_text or "",
                input_json_schema=task.input_json_schema,
                output_json_schema=task.output_json_schema,
                default_run_config_id=task.default_run_config_id,
            ),
            dataset=_dataset_stats(task),
            docs=_docs_stats(project),
            search_tools=_search_tools_block(project),
            prompts=_prompts_block(task, project, task_run_configs),
            specs=_specs_block(task),
            evals=_evals_block(task),
            tool_servers=_tool_servers_block(project),
            run_configs=_run_configs_block(task, task_run_configs),
            fine_tunes=_fine_tunes_block(task),
            prompt_optimization_jobs=_prompt_optimization_jobs_block(task),
            skills=_skills_block(project),
            connected_providers=await _connected_providers_block(),
        )
