import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.run_config import (
    MCPToolReference,
    RunConfigKind,
    RunConfigProperties,
)


def _valid_llm_run_config() -> RunConfigProperties:
    return RunConfigProperties(
        kind=RunConfigKind.kiln_agent,
        model_name="gpt-4o",
        model_provider_name=ModelProviderName.openai,
        prompt_id="simple_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_mode,
        top_p=1.0,
        temperature=1.0,
    )


def test_run_config_defaults_to_llm() -> None:
    run_config = RunConfigProperties(
        model_name="gpt-4o",
        model_provider_name=ModelProviderName.openai,
        prompt_id="simple_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_mode,
        top_p=1.0,
        temperature=1.0,
    )

    assert run_config.kind == RunConfigKind.kiln_agent


def test_run_config_llm_requires_fields() -> None:
    with pytest.raises(ValidationError, match="Field required"):
        RunConfigProperties(
            kind=RunConfigKind.kiln_agent,
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_mode,
            top_p=1.0,
            temperature=1.0,
        )


def test_run_config_llm_forbids_mcp_tool() -> None:
    with pytest.raises(
        ValueError, match="mcp_tool must not be set when kind is kiln_agent"
    ):
        RunConfigProperties(
            kind=RunConfigKind.kiln_agent,
            model_name="gpt-4o",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_mode,
            top_p=1.0,
            temperature=1.0,
            mcp_tool=MCPToolReference(
                tool_id="mcp::local::server_id::tool_name",
            ),
        )


def test_run_config_mcp_requires_tool() -> None:
    with pytest.raises(ValueError, match="mcp_tool is required when kind is mcp"):
        RunConfigProperties(kind=RunConfigKind.mcp)


def test_run_config_mcp_enforces_model_name() -> None:
    with pytest.raises(
        ValueError, match="model_name must be 'mcp_tool' when kind is mcp"
    ):
        RunConfigProperties(
            kind=RunConfigKind.mcp,
            mcp_tool=MCPToolReference(
                tool_id="mcp::local::server_id::tool_name",
            ),
            model_name="custom_model",
            model_provider_name=ModelProviderName.mcp_provider,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
            top_p=1.0,
            temperature=1.0,
        )


def test_run_config_mcp_enforces_model_provider() -> None:
    with pytest.raises(
        ValueError,
        match="model_provider_name must be 'mcp_provider' when kind is mcp",
    ):
        RunConfigProperties(
            kind=RunConfigKind.mcp,
            mcp_tool=MCPToolReference(
                tool_id="mcp::local::server_id::tool_name",
            ),
            model_name="mcp_tool",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
            top_p=1.0,
            temperature=1.0,
        )


def test_run_config_mcp_enforces_prompt_id() -> None:
    with pytest.raises(
        ValueError,
        match="prompt_id must be 'simple_prompt_builder' when kind is mcp",
    ):
        RunConfigProperties(
            kind=RunConfigKind.mcp,
            mcp_tool=MCPToolReference(
                tool_id="mcp::local::server_id::tool_name",
            ),
            model_name="mcp_tool",
            model_provider_name=ModelProviderName.mcp_provider,
            prompt_id="short_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
            top_p=1.0,
            temperature=1.0,
        )


def test_run_config_mcp_enforces_structured_output_mode() -> None:
    with pytest.raises(
        ValueError,
        match="structured_output_mode must be default when kind is mcp",
    ):
        RunConfigProperties(
            kind=RunConfigKind.mcp,
            mcp_tool=MCPToolReference(
                tool_id="mcp::local::server_id::tool_name",
            ),
            model_name="mcp_tool",
            model_provider_name=ModelProviderName.mcp_provider,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_mode,
            top_p=1.0,
            temperature=1.0,
        )


def test_run_config_mcp_enforces_sampling_defaults() -> None:
    with pytest.raises(ValueError, match=r"top_p must be 1\.0 when kind is mcp"):
        RunConfigProperties(
            kind=RunConfigKind.mcp,
            mcp_tool=MCPToolReference(
                tool_id="mcp::local::server_id::tool_name",
            ),
            model_name="mcp_tool",
            model_provider_name=ModelProviderName.mcp_provider,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
            top_p=0.5,
            temperature=1.0,
        )

    with pytest.raises(ValueError, match=r"temperature must be 1\.0 when kind is mcp"):
        RunConfigProperties(
            kind=RunConfigKind.mcp,
            mcp_tool=MCPToolReference(
                tool_id="mcp::local::server_id::tool_name",
            ),
            model_name="mcp_tool",
            model_provider_name=ModelProviderName.mcp_provider,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
            top_p=1.0,
            temperature=0.5,
        )


def test_run_config_mcp_forbids_tools_config() -> None:
    with pytest.raises(
        ValueError, match="tools_config must not be set when kind is mcp"
    ):
        RunConfigProperties(
            kind=RunConfigKind.mcp,
            mcp_tool=MCPToolReference(
                tool_id="mcp::local::server_id::tool_name",
            ),
            model_name="mcp_tool",
            model_provider_name=ModelProviderName.mcp_provider,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
            top_p=1.0,
            temperature=1.0,
            tools_config={"tools": ["kiln_tool::add_numbers"]},
        )


def test_run_config_mcp_success() -> None:
    run_config = RunConfigProperties(
        kind=RunConfigKind.mcp,
        mcp_tool=MCPToolReference(
            tool_id="mcp::local::server_id::tool_name",
        ),
    )
    assert run_config.kind == RunConfigKind.mcp


def test_run_config_mcp_defaults_applied() -> None:
    run_config = RunConfigProperties(
        kind=RunConfigKind.mcp,
        mcp_tool=MCPToolReference(
            tool_id="mcp::local::server_id::tool_name",
        ),
    )

    assert run_config.model_name == "mcp_tool"
    assert run_config.model_provider_name == ModelProviderName.mcp_provider
    assert run_config.prompt_id == "simple_prompt_builder"
    assert run_config.structured_output_mode == StructuredOutputMode.default
    assert run_config.top_p == 1.0
    assert run_config.temperature == 1.0


def test_run_config_llm_enforces_numeric_bounds() -> None:
    config = _valid_llm_run_config()
    config.top_p = 2.0
    with pytest.raises(ValueError, match="top_p must be between 0 and 1"):
        RunConfigProperties.model_validate(config.model_dump())

    config = _valid_llm_run_config()
    config.temperature = 3.0
    with pytest.raises(ValueError, match="temperature must be between 0 and 2"):
        RunConfigProperties.model_validate(config.model_dump())
