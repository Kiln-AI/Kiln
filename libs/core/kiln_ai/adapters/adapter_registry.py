from typing import TYPE_CHECKING, Literal, Union

from kiln_ai import datamodel
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.adapters.model_adapters.litellm_adapter import (
    LiteLlmAdapter,
    LiteLlmConfig,
)
from kiln_ai.adapters.model_adapters.mcp_adapter import MCPAdapter
from kiln_ai.adapters.provider_tools import (
    core_provider,
    find_user_model,
    lite_llm_core_config_for_provider,
)
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
)
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.datamodel.task_output import DataSource
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

if TYPE_CHECKING:
    from kiln_ai.adapters.model_adapters.base_adapter import (
        AiSdkStreamResult,
        OpenAIStreamResult,
    )


async def run_task(
    kiln_task: datamodel.Task,
    run_config_properties: RunConfigProperties,
    task_run: datamodel.TaskRun | str | None = None,
    new_input: str | dict | None = None,
    input_source: DataSource | None = None,
    adapter_config: AdapterConfig | None = None,
    stream_mode: Literal["sync", "openai", "ai_sdk"] = "sync",
) -> Union[
    datamodel.TaskRun, "OpenAIStreamResult", "AiSdkStreamResult"
]:
    """
    Unified task execution helper.

    Accepts an optional task_run (or equivalent id): if provided, continue that run;
    if not, start a new run from scratch.

    Args:
        kiln_task: The task to execute
        run_config_properties: Configuration for the run (model, provider, etc.)
        task_run: Optional existing TaskRun or task run ID to continue from.
                  If provided, the prior run's trace will be used.
        new_input: Input for the task. Accepts both plain text (str) and
                  structured input (dict). Maps to plaintext_input or structured_input.
        input_source: Optional DataSource for the input
        adapter_config: Optional AdapterConfig (e.g., to control whether the run is persisted/saved)
        stream_mode: How to execute the task. "sync" for normal invoke,
                    "openai" for OpenAI-style streaming, "ai_sdk" for AI SDK streaming.
                    Note: streaming modes return an async iterable, not a TaskRun.

    Returns:
        For stream_mode="sync": The resulting TaskRun
        For stream_mode="openai": OpenAIStreamResult (async iterable of chunks)
        For stream_mode="ai_sdk": AiSdkStreamResult (async iterable of events)

    Raises:
        ValueError: If task_run is provided but has no trace available
        ValueError: If input is not provided
    """
    # Validate input is provided
    if new_input is None:
        raise ValueError("Input is required. Provide new_input as either str or dict.")

    # Resolve task_run to a prior_trace if provided
    prior_trace = None
    if task_run is not None:
        if isinstance(task_run, str):
            # Look up by ID
            task_run = datamodel.TaskRun.from_id_and_parent_path(
                task_run, kiln_task.path
            )
            if task_run is None:
                raise ValueError(f"TaskRun not found: {task_run}")

        if task_run.trace is None:
            raise ValueError(
                "Cannot continue run: no trace available from the prior run."
            )
        prior_trace = task_run.trace

    # Get the adapter
    adapter = adapter_for_task(
        kiln_task,
        run_config_properties=run_config_properties,
        base_adapter_config=adapter_config,
    )

    # Execute based on stream_mode
    if stream_mode == "sync":
        return await adapter.invoke(new_input, input_source, prior_trace)
    elif stream_mode == "openai":
        return adapter.invoke_openai_stream(new_input, input_source, prior_trace)
    elif stream_mode == "ai_sdk":
        return adapter.invoke_ai_sdk_stream(new_input, input_source, prior_trace)
    else:
        raise ValueError(f"Invalid stream_mode: {stream_mode}")


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
        try:
            openai_compatible_provider_name, model_id = model_id.split("::")
        except Exception:
            raise ValueError(f"Invalid openai compatible model ID: {model_id}")

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
