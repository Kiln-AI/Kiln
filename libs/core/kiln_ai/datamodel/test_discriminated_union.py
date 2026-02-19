from kiln_ai.datamodel import PromptGenerators, StructuredOutputMode
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
    MCPToolReference,
    RunConfigProperties,
)
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.task_output import raise_exhaustive_enum_error


def is_kiln_agent_run_config_properties(
    run_config_properties: RunConfigProperties,
) -> KilnAgentRunConfigProperties:
    if run_config_properties.type != "kiln_agent" or not isinstance(
        run_config_properties, KilnAgentRunConfigProperties
    ):
        raise ValueError(
            "Run config properties is not a Kiln agent run config properties"
        )
    return run_config_properties


def is_mcp_run_config_properties(
    run_config_properties: RunConfigProperties,
) -> McpRunConfigProperties:
    if run_config_properties.type != "mcp" or not isinstance(
        run_config_properties, McpRunConfigProperties
    ):
        raise ValueError("Run config properties is not a MCP run config properties")
    return run_config_properties


def test_run_config_properties_to_dict():
    kiln_agent_config = KilnAgentRunConfigProperties(
        type="kiln_agent",
        model_name="gpt-4",
        model_provider_name=ModelProviderName.openai,
        prompt_id=PromptGenerators.SIMPLE,
        structured_output_mode=StructuredOutputMode.json_schema,
    )

    mcp_config = McpRunConfigProperties(
        type="mcp",
        tool_reference=MCPToolReference(tool_id="mcp::local::server_id::tool_name"),
    )

    task_run_config_kiln_agent = TaskRunConfig(
        name="Test Task Run Config",
        run_config_properties=kiln_agent_config,
        parent=None,
    )

    task_run_config_mcp = TaskRunConfig(
        name="Test Task Run Config",
        run_config_properties=mcp_config,
        parent=None,
    )

    agent_properties = task_run_config_kiln_agent.run_config_properties
    if agent_properties.type == "kiln_agent":
        # actual_properties is of type KilnAgentRunConfigProperties
        actual_properties = agent_properties

        # common fields should be available regardless of the type
        the_type = actual_properties.type

        # Kiln Agent-specific fields are available via typing
        special_kiln_agent_field = actual_properties.prompt_id
        special_kiln_agent_field_2 = actual_properties.temperature

        # MCP-specific fields should not be available via typing, but "ty" typechecker does not understand
        # the discriminated union and gives you all the possible fields of the entire union
        special_mcp_field = actual_properties.tool_reference

        # normal casting works, but defeats the purpose
        properties_cast = is_kiln_agent_run_config_properties(actual_properties)
        props = properties_cast
        _ = props.prompt_id
        _ = props.temperature

        # correctly flagged as Unknown by "ty" typechecker
        _ = props.tool_reference

    mcp_properties = task_run_config_mcp.run_config_properties
    if mcp_properties.type == "mcp":
        # actual_properties is of type McpRunConfigProperties
        actual_properties = mcp_properties

        # common fields should be available regardless of the type
        the_type = actual_properties.type

        # MCP-specific fields are available via typing
        special_mcp_field = actual_properties.tool_reference

        # Kiln Agent-specific fields should not be available via typing, but "ty" typechecker does not understand
        # the discriminated union and gives you all the possible fields of the entire union
        special_kiln_agent_field = actual_properties.prompt_id
        special_kiln_agent_field_2 = actual_properties.temperature

        # normal casting works, but defeats the purpose
        properties_cast = is_mcp_run_config_properties(actual_properties)
        props = properties_cast
        _ = props.tool_reference

        # correctly flagged as Unknown by "ty" typechecker
        _ = props.prompt_id
        _ = props.temperature

    match actual_properties.type:
        case "mcp":
            # "ty" cannot narrow this down either - pyright can
            _ = actual_properties.tool_reference

            # these two should not be available but "ty" typechecker still thinks they are
            _ = actual_properties.prompt_id
            _ = actual_properties.temperature
        case "kiln_agent":
            # "ty" cannot narrow this down - pyright can
            _ = actual_properties.prompt_id
            _ = actual_properties.temperature

            # this one should not be available but "ty" typechecker still thinks it is
            _ = actual_properties.tool_reference
        case _:
            raise_exhaustive_enum_error(actual_properties.type)
