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
        kind=RunConfigKind.llm,
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

    assert run_config.kind == RunConfigKind.llm


def test_run_config_llm_requires_fields() -> None:
    with pytest.raises(ValidationError, match="Field required"):
        RunConfigProperties(
            kind=RunConfigKind.llm,
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_mode,
            top_p=1.0,
            temperature=1.0,
        )


def test_run_config_llm_forbids_mcp_tool() -> None:
    with pytest.raises(ValueError, match="mcp_tool must not be set when kind is llm"):
        RunConfigProperties(
            kind=RunConfigKind.llm,
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


def test_run_config_mcp_allows_llm_fields() -> None:
    run_config = RunConfigProperties(
        kind=RunConfigKind.mcp,
        mcp_tool=MCPToolReference(
            tool_id="mcp::local::server_id::tool_name",
        ),
        model_name="custom_model",
    )
    assert run_config.kind == RunConfigKind.mcp
    assert run_config.model_name == "custom_model"


def test_run_config_llm_enforces_numeric_bounds() -> None:
    config = _valid_llm_run_config()
    config.top_p = 2.0
    with pytest.raises(ValueError, match="top_p must be between 0 and 1"):
        RunConfigProperties.model_validate(config.model_dump())

    config = _valid_llm_run_config()
    config.temperature = 3.0
    with pytest.raises(ValueError, match="temperature must be between 0 and 2"):
        RunConfigProperties.model_validate(config.model_dump())
