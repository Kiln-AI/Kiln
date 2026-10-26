from kiln_ai import datamodel
from kiln_ai.adapters.ml_model_list import ModelAdapterId, ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import (
    AdapterConfig,
    BaseAdapter,
    SkillsDict,
    assemble_unique_agent_tools,
)
from kiln_ai.adapters.model_adapters.jev_adapter import JevAdapter
from kiln_ai.adapters.model_adapters.litellm_adapter import (
    LiteLlmAdapter,
    LiteLlmConfig,
)
from kiln_ai.adapters.model_adapters.mcp_adapter import MCPAdapter
from kiln_ai.adapters.provider_tools import (
    core_provider,
    find_user_model,
    kiln_model_provider_from,
    lite_llm_core_config_for_provider,
)
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
    as_kiln_agent_run_config,
)
from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.datamodel.tool_id import (
    SKILL_TOOL_ID_PREFIX,
    WORLD_TOOL_ID_PREFIX,
    skill_id_from_tool_id,
    world_and_tool_name_from_id,
)
from kiln_ai.datamodel.world import World
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def load_skills_from_tool_ids(
    task: datamodel.Task,
    tool_ids: list[str],
    require_all: bool = False,
) -> SkillsDict:
    """Load Skill objects for any skill tool IDs in the given list.

    Performs a single directory scan of the parent project to resolve all
    referenced skills at once. Unresolvable skill IDs are silently dropped
    unless require_all is set, in which case they raise ValueError.
    """
    skill_ids = {
        skill_id_from_tool_id(tid)
        for tid in tool_ids
        if tid.startswith(SKILL_TOOL_ID_PREFIX)
    }
    if not skill_ids:
        return {}
    project = task.parent_project()
    skills = (
        Skill.from_ids_and_parent_path(skill_ids, project.path)
        if project is not None
        else {}
    )
    if require_all:
        missing_skill_ids = sorted(skill_ids - set(skills.keys()))
        if missing_skill_ids:
            raise ValueError(
                "Skill(s) referenced in run config not found in the project: "
                f"{', '.join(missing_skill_ids)}"
            )
    return skills


def load_skills_for_task(
    task: datamodel.Task,
    run_config: RunConfigProperties,
) -> SkillsDict:
    """Pre-load all skills referenced by a run config in a single directory scan.

    Call once at the orchestration layer and pass the result to adapter(s) via
    AdapterConfig(skills=...).
    """
    if run_config.type != "kiln_agent":
        return {}
    tool_config = as_kiln_agent_run_config(run_config).tools_config
    if tool_config is None or tool_config.tools is None:
        return {}
    return load_skills_from_tool_ids(task, tool_config.tools)


async def validate_run_config_tool_names(
    task: datamodel.Task,
    run_config_properties: RunConfigProperties,
) -> None:
    """Reject a run config whose tools would fail at runtime.

    Resolves every attached project tool and skill, raising ValueError when a
    referenced skill does not exist or two tools share a name (see
    assemble_unique_agent_tools). Catches collisions at selection time; the
    runtime check remains the backstop for tools renamed after the run config
    was created.

    World tools (`kiln_tool::world::<world_id>::<tool_name>`) resolve only inside
    an episode of their world, which only the eval runner starts, so they are not
    resolved here. Their world must exist in the task's project, all of them must
    come from one world (a job runs in one world), and the name the model sees
    (the id's tool_name) must not collide with another selected tool. Whether the
    world really serves that tool is checked at runtime, inside the episode.
    """
    if run_config_properties.type != "kiln_agent":
        return
    tools_config = as_kiln_agent_run_config(run_config_properties).tools_config
    if tools_config is None or not tools_config.tools:
        return
    world_tool_ids = [
        tid for tid in tools_config.tools if tid.startswith(WORLD_TOOL_ID_PREFIX)
    ]
    project_tool_ids = [
        tid for tid in tools_config.tools if not tid.startswith(WORLD_TOOL_ID_PREFIX)
    ]
    skills = load_skills_from_tool_ids(task, project_tool_ids, require_all=True)
    tools = await assemble_unique_agent_tools(
        task, project_tool_ids, list(skills.values())
    )
    if world_tool_ids:
        tool_names = [await tool.name() for tool in tools]
        validate_world_tool_ids(task, world_tool_ids, tool_names)


def validate_world_tool_ids(
    task: datamodel.Task,
    world_tool_ids: list[str],
    project_tool_names: list[str],
) -> None:
    """Check a run config's world tool ids without an active episode.

    Raises ValueError when a world is not in the task's project, when the ids
    name more than one world, or when a world tool's name collides with another
    world tool or with one of *project_tool_names* (the names of the run config's
    resolved project tools, including the "skill" tool when skills are selected).
    """
    world_and_tool_names = [world_and_tool_name_from_id(t) for t in world_tool_ids]
    world_ids = sorted({world_id for world_id, _ in world_and_tool_names})

    project = task.parent_project()
    if project is None:
        raise ValueError(
            "World tools require the task to belong to a project: "
            f"{', '.join(world_tool_ids)}"
        )
    found = World.from_ids_and_parent_path(set(world_ids), project.path, readonly=True)
    missing = [world_id for world_id in world_ids if world_id not in found]
    if missing:
        raise ValueError(
            f"World(s) {', '.join(missing)} referenced by world tools in the run "
            f"config not found in project {project.id}. Create the world first, or "
            "remove its tools from the run config."
        )
    if len(world_ids) > 1:
        raise ValueError(
            f"Run config lists tools from more than one world ({', '.join(world_ids)}). "
            "A job runs in one world, so all world tools must come from the same world."
        )

    tool_names = project_tool_names + [name for _, name in world_and_tool_names]
    if len(tool_names) != len(set(tool_names)):
        duplicates = sorted({n for n in tool_names if tool_names.count(n) > 1})
        raise ValueError(
            f"Multiple selected tools share the same function name: {', '.join(duplicates)}. "
            "A world tool's name is the last segment of its id. Each tool must have a "
            "unique name: de-select the duplicate tools, or rename the project tools."
        )


def litellm_core_provider_config(
    run_config_properties: KilnAgentRunConfigProperties,
) -> LiteLlmConfig:
    # For things like the fine-tune provider, we want to run the underlying provider (e.g. openai)
    core_provider_name = core_provider(
        run_config_properties.model_name, run_config_properties.model_provider_name
    )

    # Resolve openai_compatible_provider_name for providers that need it.
    # Two cases need this:
    # 1. user_model_registry entries with custom providers (provider_type="custom")
    # 2. Legacy openai_compatible providers (model_name format: "provider_name::model_id")
    openai_compatible_provider_name = None
    user_model_provider = find_user_model(run_config_properties.model_name)
    if (
        user_model_provider
        and user_model_provider.openai_compatible_provider_name is not None
    ):
        openai_compatible_provider_name = (
            user_model_provider.openai_compatible_provider_name
        )
    elif (
        run_config_properties.model_provider_name == ModelProviderName.openai_compatible
        and not run_config_properties.model_name.startswith("user_model::")
    ):
        # Legacy openai_compatible model ids are "provider_name::model_id". We pull the
        # provider name out for base_url lookup, but keep the full slug on the run config
        # so it is faithfully persisted to disk and can be rehydrated later (e.g. on repair).
        model_id = run_config_properties.model_name
        if "::" not in model_id:
            raise ValueError(f"Invalid openai compatible model ID: {model_id}")
        provider_part, model_part = model_id.split("::", 1)
        if not provider_part or not model_part:
            raise ValueError(f"Invalid openai compatible model ID: {model_id}")
        openai_compatible_provider_name = provider_part

    config = lite_llm_core_config_for_provider(
        core_provider_name, openai_compatible_provider_name
    )
    if config is None:
        raise ValueError(
            "Fine tune or custom openai compatible provider is not a core provider. The underlying provider should be used when requesting the adapter litellm config instead."
        )

    return LiteLlmConfig(
        run_config_properties=run_config_properties,
        base_url=config.base_url,
        default_headers=config.default_headers,
        additional_body_options=config.additional_body_options or {},
    )


def adapter_for_task(
    kiln_task: datamodel.Task,
    run_config_properties: RunConfigProperties,
    base_adapter_config: AdapterConfig | None = None,
) -> BaseAdapter:
    match run_config_properties.type:
        case "mcp":
            if not isinstance(run_config_properties, McpRunConfigProperties):
                raise ValueError("McpRunConfigProperties is required for MCP adapter")
            return MCPAdapter(
                task=kiln_task,
                run_config=run_config_properties,
                config=base_adapter_config,
            )
        case "kiln_agent":
            if not isinstance(run_config_properties, KilnAgentRunConfigProperties):
                raise ValueError(
                    "KilnAgentRunConfigProperties is required for kiln_agent adapters"
                )
            model_provider = kiln_model_provider_from(
                run_config_properties.model_name,
                run_config_properties.model_provider_name,
            )
            match model_provider.adapter:
                case ModelAdapterId.jev:
                    return JevAdapter(
                        kiln_task=kiln_task,
                        run_config=run_config_properties,
                        base_adapter_config=base_adapter_config,
                    )
                case ModelAdapterId.litellm:
                    return LiteLlmAdapter(
                        kiln_task=kiln_task,
                        config=litellm_core_provider_config(run_config_properties),
                        base_adapter_config=base_adapter_config,
                    )
                case _:
                    raise_exhaustive_enum_error(model_provider.adapter)
        case _:
            raise_exhaustive_enum_error(run_config_properties.type)
