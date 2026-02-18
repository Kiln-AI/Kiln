import json

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredOutputMode,
)
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
    MCPToolReference,
    RunConfigProperties,
    ToolsRunConfig,
)

run_config_adapter = TypeAdapter(RunConfigProperties)


class RunConfigWrapper(BaseModel):
    run_config_properties: RunConfigProperties


LEGACY_KILN_AGENT_JSON = {
    "model_name": "gpt-4",
    "model_provider_name": "openai",
    "prompt_id": "simple_prompt_builder",
    "structured_output_mode": "json_schema",
}

KILN_AGENT_JSON = {
    "type": "kiln_agent",
    "model_name": "gpt-4",
    "model_provider_name": "openai",
    "prompt_id": "simple_prompt_builder",
    "structured_output_mode": "json_schema",
}

MCP_JSON = {
    "type": "mcp",
    "tool_reference": {
        "tool_id": "mcp::local::server_id::tool_name",
    },
}


class TestKilnAgentRunConfigProperties:
    def test_direct_construction(self):
        config = KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        )
        assert config.type == "kiln_agent"
        assert config.model_name == "gpt-4"
        assert config.model_provider_name == ModelProviderName.openai
        assert config.top_p == 1.0
        assert config.temperature == 1.0
        assert config.tools_config is None

    def test_type_defaults_to_kiln_agent(self):
        config = KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        )
        assert config.type == "kiln_agent"

    def test_type_serialized_in_output(self):
        config = KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        )
        data = config.model_dump()
        assert data["type"] == "kiln_agent"

    def test_validation_top_p(self):
        with pytest.raises(ValidationError, match="top_p must be between 0 and 1"):
            KilnAgentRunConfigProperties(
                model_name="gpt-4",
                model_provider_name=ModelProviderName.openai,
                prompt_id=PromptGenerators.SIMPLE,
                structured_output_mode=StructuredOutputMode.json_schema,
                top_p=1.5,
            )

    def test_validation_temperature(self):
        with pytest.raises(
            ValidationError, match="temperature must be between 0 and 2"
        ):
            KilnAgentRunConfigProperties(
                model_name="gpt-4",
                model_provider_name=ModelProviderName.openai,
                prompt_id=PromptGenerators.SIMPLE,
                structured_output_mode=StructuredOutputMode.json_schema,
                temperature=3.0,
            )

    def test_with_tools_config(self):
        config = KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
            tools_config=ToolsRunConfig(tools=["kiln_tool::add_numbers"]),
        )
        assert config.tools_config is not None
        assert config.tools_config.tools == ["kiln_tool::add_numbers"]


class TestMcpRunConfigProperties:
    def test_direct_construction(self):
        config = McpRunConfigProperties(
            type="mcp",
            tool_reference=MCPToolReference(tool_id="mcp::local::server_id::tool_name"),
        )
        assert config.type == "mcp"
        assert config.tool_reference.tool_id == "mcp::local::server_id::tool_name"

    def test_type_serialized_in_output(self):
        config = McpRunConfigProperties(
            type="mcp",
            tool_reference=MCPToolReference(tool_id="mcp::local::server_id::tool_name"),
        )
        data = config.model_dump()
        assert data["type"] == "mcp"
        assert data["tool_reference"]["tool_id"] == "mcp::local::server_id::tool_name"

    def test_missing_tool_reference_raises(self):
        with pytest.raises(ValidationError):
            McpRunConfigProperties(type="mcp")  # type: ignore

    def test_missing_type_raises(self):
        config = McpRunConfigProperties(
            tool_reference=MCPToolReference(tool_id="mcp::local::server_id::tool_name")
        )
        assert config.type == "mcp"


class TestDiscriminatedUnion:
    def test_kiln_agent_via_type_adapter(self):
        config = run_config_adapter.validate_python(KILN_AGENT_JSON)
        assert isinstance(config, KilnAgentRunConfigProperties)
        assert config.type == "kiln_agent"
        assert config.model_name == "gpt-4"

    def test_mcp_via_type_adapter(self):
        config = run_config_adapter.validate_python(MCP_JSON)
        assert isinstance(config, McpRunConfigProperties)
        assert config.type == "mcp"
        assert config.tool_reference.tool_id == "mcp::local::server_id::tool_name"

    def test_kiln_agent_via_wrapper_model(self):
        wrapper = RunConfigWrapper(run_config_properties=KILN_AGENT_JSON)
        assert isinstance(wrapper.run_config_properties, KilnAgentRunConfigProperties)

    def test_mcp_via_wrapper_model(self):
        wrapper = RunConfigWrapper(run_config_properties=MCP_JSON)
        assert isinstance(wrapper.run_config_properties, McpRunConfigProperties)

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            run_config_adapter.validate_python({"type": "unknown_type"})


class TestBackwardCompatibility:
    def test_legacy_json_via_type_adapter(self):
        config = run_config_adapter.validate_python(LEGACY_KILN_AGENT_JSON)
        assert isinstance(config, KilnAgentRunConfigProperties)
        assert config.type == "kiln_agent"
        assert config.model_name == "gpt-4"
        assert config.model_provider_name == ModelProviderName.openai

    def test_legacy_json_via_wrapper_model(self):
        wrapper = RunConfigWrapper(run_config_properties=LEGACY_KILN_AGENT_JSON)
        assert isinstance(wrapper.run_config_properties, KilnAgentRunConfigProperties)
        assert wrapper.run_config_properties.model_name == "gpt-4"

    def test_legacy_json_roundtrip(self):
        config = run_config_adapter.validate_python(LEGACY_KILN_AGENT_JSON)
        dumped = config.model_dump()
        assert dumped["type"] == "kiln_agent"
        reloaded = run_config_adapter.validate_python(dumped)
        assert isinstance(reloaded, KilnAgentRunConfigProperties)
        assert reloaded.model_name == config.model_name

    def test_legacy_json_string_roundtrip(self):
        config = run_config_adapter.validate_python(LEGACY_KILN_AGENT_JSON)
        json_str = json.dumps(config.model_dump())
        reloaded = run_config_adapter.validate_python(json.loads(json_str))
        assert isinstance(reloaded, KilnAgentRunConfigProperties)
        assert reloaded.model_name == "gpt-4"
        assert reloaded.type == "kiln_agent"


class TestTaskRunConfigDecode:
    def test_mcp_task_run_config_from_dict(self):
        from kiln_ai.datamodel.task import Task, TaskRunConfig

        task = Task(name="Test Task", instruction="Test instruction")
        config = TaskRunConfig(
            name="MCP Config",
            run_config_properties=McpRunConfigProperties(
                type="mcp",
                tool_reference=MCPToolReference(
                    tool_id="mcp::local::server_id::tool_name"
                ),
            ),
            parent=task,
        )
        assert isinstance(config.run_config_properties, McpRunConfigProperties)
        assert config.run_config_properties.type == "mcp"
        assert (
            config.run_config_properties.tool_reference.tool_id
            == "mcp::local::server_id::tool_name"
        )

    def test_mcp_task_run_config_loading_from_file(self):
        from kiln_ai.datamodel.task import TaskRunConfig

        raw_data = {
            "v": 1,
            "name": "MCP Config",
            "run_config_properties": {
                "type": "mcp",
                "tool_reference": {
                    "tool_id": "mcp::local::server_id::tool_name",
                },
            },
        }
        config = TaskRunConfig.model_validate(
            raw_data, context={"loading_from_file": True}
        )
        assert isinstance(config.run_config_properties, McpRunConfigProperties)
        assert config.run_config_properties.type == "mcp"
        assert (
            config.run_config_properties.tool_reference.tool_id
            == "mcp::local::server_id::tool_name"
        )
        dumped = config.run_config_properties.model_dump()
        assert "structured_output_mode" not in dumped

    def test_legacy_kiln_agent_task_run_config_loading_from_file(self):
        from kiln_ai.datamodel.task import TaskRunConfig

        raw_data = {
            "v": 1,
            "name": "Legacy Config",
            "run_config_properties": {
                "model_name": "gpt-4",
                "model_provider_name": "openai",
                "prompt_id": "simple_prompt_builder",
            },
        }
        config = TaskRunConfig.model_validate(
            raw_data, context={"loading_from_file": True}
        )
        assert isinstance(config.run_config_properties, KilnAgentRunConfigProperties)
        assert config.run_config_properties.type == "kiln_agent"
        assert (
            config.run_config_properties.structured_output_mode
            == StructuredOutputMode.unknown
        )


class TestSaveLoadBothTypes:
    def test_kiln_agent_roundtrip(self):
        original = KilnAgentRunConfigProperties(
            model_name="claude-3.5-sonnet",
            model_provider_name=ModelProviderName.anthropic,
            prompt_id=PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT,
            structured_output_mode=StructuredOutputMode.json_instructions,
            top_p=0.9,
            temperature=0.7,
        )
        dumped = json.loads(json.dumps(original.model_dump()))
        restored = run_config_adapter.validate_python(dumped)
        assert isinstance(restored, KilnAgentRunConfigProperties)
        assert restored.type == "kiln_agent"
        assert restored.model_name == "claude-3.5-sonnet"
        assert restored.top_p == 0.9
        assert restored.temperature == 0.7

    def test_mcp_roundtrip(self):
        original = McpRunConfigProperties(
            type="mcp",
            tool_reference=MCPToolReference(tool_id="mcp::local::server_id::tool_name"),
        )
        dumped = json.loads(json.dumps(original.model_dump()))
        restored = run_config_adapter.validate_python(dumped)
        assert isinstance(restored, McpRunConfigProperties)
        assert restored.type == "mcp"
        assert restored.tool_reference.tool_id == "mcp::local::server_id::tool_name"

    def test_wrapper_kiln_agent_roundtrip(self):
        wrapper = RunConfigWrapper(
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="gpt-4",
                model_provider_name=ModelProviderName.openai,
                prompt_id=PromptGenerators.SIMPLE,
                structured_output_mode=StructuredOutputMode.json_schema,
            )
        )
        dumped = json.loads(wrapper.model_dump_json())
        restored = RunConfigWrapper.model_validate(dumped)
        assert isinstance(restored.run_config_properties, KilnAgentRunConfigProperties)

    def test_wrapper_mcp_roundtrip(self):
        wrapper = RunConfigWrapper(
            run_config_properties=McpRunConfigProperties(
                type="mcp",
                tool_reference=MCPToolReference(
                    tool_id="mcp::local::server_id::tool_name"
                ),
            )
        )
        dumped = json.loads(wrapper.model_dump_json())
        restored = RunConfigWrapper.model_validate(dumped)
        assert isinstance(restored.run_config_properties, McpRunConfigProperties)
