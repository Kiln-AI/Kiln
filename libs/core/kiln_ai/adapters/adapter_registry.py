from kiln_ai import datamodel
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.adapters.model_adapters.litellm_adapter import (
    LiteLlmAdapter,
    LiteLlmConfig,
)
from kiln_ai.adapters.provider_tools import (
    core_provider,
    get_provider_connection_details,
    lite_llm_config_for_openai_compatible,
)
from kiln_ai.datamodel.task import RunConfigProperties


def adapter_for_task(
    kiln_task: datamodel.Task,
    run_config_properties: RunConfigProperties,
    base_adapter_config: AdapterConfig | None = None,
) -> BaseAdapter:
    # Get the provider to run. For things like the fine-tune provider, we want to run the underlying provider
    core_provider_name = core_provider(
        run_config_properties.model_name, run_config_properties.model_provider_name
    )

    # openai compatible providers are handled separately since they have custom config logic
    if core_provider_name == ModelProviderName.openai_compatible:
        config = lite_llm_config_for_openai_compatible(run_config_properties)
        return LiteLlmAdapter(
            kiln_task=kiln_task,
            config=config,
            base_adapter_config=base_adapter_config,
        )

    provider_connection_details = get_provider_connection_details(core_provider_name)

    # we need to extract these to pass them as separate arguments to the LiteLlmConfig
    default_headers = provider_connection_details.pop("default_headers", None)
    base_url = provider_connection_details.pop("base_url", None)

    return LiteLlmAdapter(
        kiln_task=kiln_task,
        config=LiteLlmConfig(
            run_config_properties=run_config_properties,
            base_url=base_url,
            default_headers=default_headers,
            additional_body_options=provider_connection_details,
        ),
        base_adapter_config=base_adapter_config,
    )
