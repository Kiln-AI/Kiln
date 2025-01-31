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
from kiln_ai.utils.config import Config


def adapter_for_task(
    kiln_task: datamodel.Task,
    model_name: str,
    provider: str | None = None,
    prompt_builder: BasePromptBuilder | None = None,
    tags: list[str] | None = None,
) -> BaseAdapter:
    if provider == ModelProviderName.openrouter:
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

    # We use langchain for all others right now, but moving off it as we touch anything.
    return LangchainAdapter(
        kiln_task,
        model_name=model_name,
        provider=provider,
        prompt_builder=prompt_builder,
        tags=tags,
    )
