from kiln_ai import datamodel
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.adapters.model_adapters.litellm_adapter import (
    LiteLlmAdapter,
    LiteLlmConfig,
)
from kiln_ai.adapters.provider_tools import (
    core_provider,
    lite_llm_core_config_for_provider,
)
from kiln_ai.datamodel.task import RunConfigProperties


def litellm_core_provider_config(
    run_config_properties: RunConfigProperties,
) -> LiteLlmConfig:
    # For things like the fine-tune provider, we want to run the underlying provider (e.g. openai)
    core_provider_name = core_provider(
        run_config_properties.model_name, run_config_properties.model_provider_name
    )

    # For OpenAI compatible providers, we want to retrieve the underlying provider and update the run config properties to match
    openai_compatible_provider_name = None
    if run_config_properties.model_provider_name == ModelProviderName.openai_compatible:
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
    return LiteLlmAdapter(
        kiln_task=kiln_task,
        config=litellm_core_provider_config(run_config_properties),
        base_adapter_config=base_adapter_config,
    )
