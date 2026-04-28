from kiln_ai import datamodel
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import (
    AdapterConfig,
    BaseAdapter,
    SkillsDict,
)
from kiln_ai.adapters.model_adapters.litellm_adapter import (
    LiteLlmAdapter,
    LiteLlmConfig,
)
from kiln_ai.adapters.model_adapters.mcp_adapter import MCPAdapter
from kiln_ai.adapters.provider_tools import (
    core_provider,
    find_user_model,
    lite_llm_core_config_for_provider,
    resolve_openai_compatible_model_id,
)
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
    as_kiln_agent_run_config,
)
from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.datamodel.tool_id import SKILL_TOOL_ID_PREFIX, skill_id_from_tool_id
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def load_skills_from_tool_ids(
    task: datamodel.Task,
    tool_ids: list[str],
) -> SkillsDict:
    """Load Skill objects for any skill tool IDs in the given list.

    Performs a single directory scan of the parent project to resolve all
    referenced skills at once.
    """
    skill_ids = {
        skill_id_from_tool_id(tid)
        for tid in tool_ids
        if tid.startswith(SKILL_TOOL_ID_PREFIX)
    }
    if not skill_ids:
        return {}
    project = task.parent_project()
    if project is None:
        return {}
    return Skill.from_ids_and_parent_path(skill_ids, project.path)


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
        model_id = run_config_properties.model_name
        openai_compatible_provider_name, model_id = resolve_openai_compatible_model_id(
            model_id
        )

        # Update a copy of the run config properties to use the openai compatible provider
        updated_run_config_properties = run_config_properties.model_copy(deep=True)
        updated_run_config_properties.model_name = model_id
        run_config_properties = updated_run_config_properties

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
                    "KilnAgentRunConfigProperties is required for LiteLlmAdapter"
                )
            return LiteLlmAdapter(
                kiln_task=kiln_task,
                config=litellm_core_provider_config(run_config_properties),
                base_adapter_config=base_adapter_config,
            )
        case _:
            raise_exhaustive_enum_error(run_config_properties.type)
