from os import getenv

from kiln_ai import datamodel
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter
from kiln_ai.adapters.model_adapters.langchain_adapters import LangchainAdapter
from kiln_ai.adapters.model_adapters.openai_model_adapter import (
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
)
from kiln_ai.adapters.prompt_builders import BasePromptBuilder
from kiln_ai.adapters.provider_tools import core_provider, openai_compatible_config
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def adapter_for_task(
    kiln_task: datamodel.Task,
    model_name: str,
    provider: ModelProviderName,
    prompt_builder: BasePromptBuilder | None = None,
    tags: list[str] | None = None,
) -> BaseAdapter:
    # Get the provider to run. For things like the fine-tune provider, we want to run the underlying provider
    core_provider_name = core_provider(model_name, provider)

    match core_provider_name:
        case ModelProviderName.openrouter:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                config=OpenAICompatibleConfig(
                    base_url=getenv("OPENROUTER_BASE_URL")
                    or "https://openrouter.ai/api/v1",
                    api_key=Config.shared().open_router_api_key,
                    model_name=model_name,
                    provider_name=provider,
                    openrouter_style_reasoning=True,
                    default_headers={
                        "HTTP-Referer": "https://getkiln.ai/openrouter",
                        "X-Title": "KilnAI",
                    },
                ),
                prompt_builder=prompt_builder,
                tags=tags,
            )
        case ModelProviderName.openai:
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                config=OpenAICompatibleConfig(
                    api_key=Config.shared().open_ai_api_key,
                    model_name=model_name,
                    provider_name=provider,
                ),
                prompt_builder=prompt_builder,
                tags=tags,
            )
        case ModelProviderName.openai_compatible:
            config = openai_compatible_config(model_name)
            return OpenAICompatibleAdapter(
                kiln_task=kiln_task,
                config=config,
                prompt_builder=prompt_builder,
                tags=tags,
            )
        # Use LangchainAdapter for the rest
        case ModelProviderName.groq:
            pass
        case ModelProviderName.amazon_bedrock:
            pass
        case ModelProviderName.ollama:
            pass
        case ModelProviderName.fireworks_ai:
            pass
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

    # We use langchain for all others right now, but moving off it as we touch anything.
    return LangchainAdapter(
        kiln_task,
        model_name=model_name,
        provider=provider,
        prompt_builder=prompt_builder,
        tags=tags,
    )
