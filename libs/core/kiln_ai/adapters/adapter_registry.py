from os import getenv

from kiln_ai import datamodel
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.adapters.model_adapters.langchain_adapters import LangchainAdapter
from kiln_ai.adapters.model_adapters.openai_model_adapter import (
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
)
from kiln_ai.adapters.provider_tools import core_provider, openai_compatible_config
from kiln_ai.datamodel import PromptId
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def adapter_for_task(
    kiln_task: datamodel.Task,
    model_name: str,
    provider: ModelProviderName,
    prompt_id: PromptId | None = None,
    base_adapter_config: AdapterConfig | None = None,
) -> BaseAdapter:
    # Get the provider to run. For things like the fine-tune provider, we want to run the underlying provider
    core_provider_name = core_provider(model_name, provider)

    match core_provider_name:
        case ModelProviderName.openrouter:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                config=OpenAICompatibleConfig(
                    litellm_provider_name="openrouter",
                    api_key=Config.shared().open_router_api_key,
                    model_name=model_name,
                    provider_name=provider,
                    default_headers={
                        "HTTP-Referer": "https://getkiln.ai/openrouter",
                        "X-Title": "KilnAI",
                    },
                ),
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
            )
        case ModelProviderName.openai:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                config=OpenAICompatibleConfig(
                    litellm_provider_name="openai",
                    api_key=Config.shared().open_ai_api_key,
                    model_name=model_name,
                    provider_name=provider,
                ),
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
            )
        case ModelProviderName.openai_compatible:
            # TODO P0 this is broken
            config = openai_compatible_config(model_name)
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                config=config,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
            )
        # Use LangchainAdapter for the rest
        case ModelProviderName.groq:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    litellm_provider_name="groq",
                    api_key=Config.shared().groq_api_key,
                    model_name=model_name,
                    provider_name=provider,
                ),
            )
        case ModelProviderName.amazon_bedrock:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    litellm_provider_name="bedrock",
                    # TODO this should be optional, or someting
                    api_key="asdf",
                    model_name=model_name,
                    provider_name=provider,
                ),
            )
        case ModelProviderName.ollama:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    litellm_provider_name="ollama",
                    # TODO this should be optional, or someting
                    api_key="asdf",
                    model_name=model_name,
                    provider_name=provider,
                ),
            )
        case ModelProviderName.fireworks_ai:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    litellm_provider_name="fireworks_ai",
                    # TODO: account ID isn't passed. And "strict" isn't allowed for tools.
                    api_key=Config.shared().fireworks_api_key,
                    model_name=model_name,
                    provider_name=provider,
                ),
            )
        case ModelProviderName.anthropic:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    litellm_provider_name="anthropic",
                    api_key=Config.shared().anthropic_api_key,
                    model_name=model_name,
                    provider_name=provider,
                ),
            )
        case ModelProviderName.gemini_api:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    litellm_provider_name="gemini",
                    api_key=Config.shared().gemini_api_key,
                    model_name=model_name,
                    provider_name=provider,
                ),
            )
        case ModelProviderName.azure:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    litellm_provider_name="azure_ai",
                    api_key=Config.shared().azure_ai_api_key,
                    # base_url=Config.shared().azure_ai_api_base,
                    model_name=model_name,
                    provider_name=provider,
                ),
            )
        case ModelProviderName.azure_openai:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                prompt_id=prompt_id,
                base_adapter_config=base_adapter_config,
                config=OpenAICompatibleConfig(
                    litellm_provider_name="azure",
                    api_key=Config.shared().azure_openai_api_key,
                    base_url=Config.shared().azure_openai_endpoint,
                    model_name=model_name,
                    provider_name=provider,
                ),
            )
        # These are virtual providers that should have mapped to an actual provider in core_provider
        case ModelProviderName.kiln_fine_tune:
            raise ValueError(
                "Fine tune is not a supported core provider. It should map to an actual provider."
            )
        case ModelProviderName.kiln_custom_registry:
            raise ValueError(
                "Custom openai compatible provider is not a supported core provider. It should map to an actual provider."
            )
        case _:
            raise_exhaustive_enum_error(core_provider_name)
