import os
from dataclasses import dataclass
from enum import Enum
from os import getenv
from typing import Any, Dict, List, NoReturn

import httpx
import requests
from langchain_aws import ChatBedrockConverse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ..utils.config import Config

"""
Provides model configuration and management for various LLM providers and models.
This module handles the integration with different AI model providers and their respective models,
including configuration, validation, and instantiation of language models.
"""


class ModelProviderName(str, Enum):
    """
    Enumeration of supported AI model providers.
    """

    openai = "openai"
    groq = "groq"
    amazon_bedrock = "amazon_bedrock"
    ollama = "ollama"
    openrouter = "openrouter"


class ModelFamily(str, Enum):
    """
    Enumeration of supported model families/architectures.
    """

    gpt = "gpt"
    llama = "llama"
    phi = "phi"
    mistral = "mistral"
    gemma = "gemma"
    gemini = "gemini"
    claude = "claude"


# Where models have instruct and raw versions, instruct is default and raw is specified
class ModelName(str, Enum):
    """
    Enumeration of specific model versions supported by the system.
    Where models have instruct and raw versions, instruct is default and raw is specified.
    """

    llama_3_1_8b = "llama_3_1_8b"
    llama_3_1_70b = "llama_3_1_70b"
    llama_3_1_405b = "llama_3_1_405b"
    llama_3_2_3b = "llama_3_2_3b"
    llama_3_2_11b = "llama_3_2_11b"
    llama_3_2_90b = "llama_3_2_90b"
    gpt_4o_mini = "gpt_4o_mini"
    gpt_4o = "gpt_4o"
    phi_3_5 = "phi_3_5"
    mistral_large = "mistral_large"
    mistral_nemo = "mistral_nemo"
    gemma_2_2b = "gemma_2_2b"
    gemma_2_9b = "gemma_2_9b"
    gemma_2_27b = "gemma_2_27b"
    claude_3_5_sonnet = "claude_3_5_sonnet"
    gemini_1_5_flash = "gemini_1_5_flash"
    gemini_1_5_flash_8b = "gemini_1_5_flash_8b"
    gemini_1_5_pro = "gemini_1_5_pro"
    nemotron_70b = "nemotron_70b"


class KilnModelProvider(BaseModel):
    """
    Configuration for a specific model provider.

    Attributes:
        name: The provider's identifier
        supports_structured_output: Whether the provider supports structured output formats
        provider_options: Additional provider-specific configuration options
    """

    name: ModelProviderName
    supports_structured_output: bool = True
    provider_options: Dict = {}


class KilnModel(BaseModel):
    """
    Configuration for a specific AI model.

    Attributes:
        family: The model's architecture family
        name: The model's identifier
        friendly_name: Human-readable name for the model
        providers: List of providers that offer this model
        supports_structured_output: Whether the model supports structured output formats
    """

    family: str
    name: str
    friendly_name: str
    providers: List[KilnModelProvider]
    supports_structured_output: bool = True


built_in_models: List[KilnModel] = [
    # GPT 4o Mini
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_4o_mini,
        friendly_name="GPT 4o Mini",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                provider_options={"model": "gpt-4o-mini"},
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "openai/gpt-4o-mini"},
            ),
        ],
    ),
    # GPT 4o
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_4o,
        friendly_name="GPT 4o",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                provider_options={"model": "gpt-4o"},
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "openai/gpt-4o-2024-08-06"},
            ),
        ],
    ),
    # Claude 3.5 Sonnet
    KilnModel(
        family=ModelFamily.claude,
        name=ModelName.claude_3_5_sonnet,
        friendly_name="Claude 3.5 Sonnet",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "anthropic/claude-3.5-sonnet"},
            ),
        ],
    ),
    # Gemini 1.5 Pro
    KilnModel(
        family=ModelFamily.gemini,
        name=ModelName.gemini_1_5_pro,
        friendly_name="Gemini 1.5 Pro",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "google/gemini-pro-1.5"},
            ),
        ],
    ),
    # Gemini 1.5 Flash
    KilnModel(
        family=ModelFamily.gemini,
        name=ModelName.gemini_1_5_flash,
        friendly_name="Gemini 1.5 Flash",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "google/gemini-flash-1.5"},
            ),
        ],
    ),
    # Gemini 1.5 Flash 8B
    KilnModel(
        family=ModelFamily.gemini,
        name=ModelName.gemini_1_5_flash_8b,
        friendly_name="Gemini 1.5 Flash 8B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "google/gemini-flash-1.5-8b"},
            ),
        ],
    ),
    # Nemotron 70B
    KilnModel(
        family=ModelFamily.llama,
        name=ModelName.nemotron_70b,
        friendly_name="Nemotron 70B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                provider_options={"model": "nvidia/llama-3.1-nemotron-70b-instruct"},
            ),
        ],
    ),
    # Llama 3.1-8b
    KilnModel(
        family=ModelFamily.llama,
        name=ModelName.llama_3_1_8b,
        friendly_name="Llama 3.1 8B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.groq,
                provider_options={"model": "llama-3.1-8b-instant"},
            ),
            KilnModelProvider(
                name=ModelProviderName.amazon_bedrock,
                supports_structured_output=False,
                provider_options={
                    "model": "meta.llama3-1-8b-instruct-v1:0",
                    "region_name": "us-west-2",  # Llama 3.1 only in west-2
                },
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                provider_options={
                    "model": "llama3.1:8b",
                    "model_aliases": ["llama3.1"],  # 8b is default
                },
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                provider_options={"model": "meta-llama/llama-3.1-8b-instruct"},
            ),
        ],
    ),
    # Llama 3.1 70b
    KilnModel(
        family=ModelFamily.llama,
        name=ModelName.llama_3_1_70b,
        friendly_name="Llama 3.1 70B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.groq,
                provider_options={"model": "llama-3.1-70b-versatile"},
            ),
            KilnModelProvider(
                name=ModelProviderName.amazon_bedrock,
                supports_structured_output=False,
                provider_options={
                    "model": "meta.llama3-1-70b-instruct-v1:0",
                    "region_name": "us-west-2",  # Llama 3.1 only in west-2
                },
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "meta-llama/llama-3.1-70b-instruct"},
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                provider_options={"model": "llama3.1:70b"},
            ),
        ],
    ),
    # Llama 3.1 405b
    KilnModel(
        family=ModelFamily.llama,
        name=ModelName.llama_3_1_405b,
        friendly_name="Llama 3.1 405B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.amazon_bedrock,
                provider_options={
                    "model": "meta.llama3-1-405b-instruct-v1:0",
                    "region_name": "us-west-2",  # Llama 3.1 only in west-2
                },
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                provider_options={"model": "llama3.1:405b"},
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "meta-llama/llama-3.1-405b-instruct"},
            ),
        ],
    ),
    # Mistral Nemo
    KilnModel(
        family=ModelFamily.mistral,
        name=ModelName.mistral_nemo,
        friendly_name="Mistral Nemo",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "mistralai/mistral-nemo"},
            ),
        ],
    ),
    # Mistral Large
    KilnModel(
        family=ModelFamily.mistral,
        name=ModelName.mistral_large,
        friendly_name="Mistral Large",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.amazon_bedrock,
                provider_options={
                    "model": "mistral.mistral-large-2407-v1:0",
                    "region_name": "us-west-2",  # only in west-2
                },
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "mistralai/mistral-large"},
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                provider_options={"model": "mistral-large"},
            ),
        ],
    ),
    # Llama 3.2 3B
    KilnModel(
        family=ModelFamily.llama,
        name=ModelName.llama_3_2_3b,
        friendly_name="Llama 3.2 3B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                provider_options={"model": "meta-llama/llama-3.2-3b-instruct"},
            ),
        ],
    ),
    # Llama 3.2 11B
    KilnModel(
        family=ModelFamily.llama,
        name=ModelName.llama_3_2_11b,
        friendly_name="Llama 3.2 11B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                provider_options={"model": "meta-llama/llama-3.2-11b-vision-instruct"},
            ),
        ],
    ),
    # Llama 3.2 90B
    KilnModel(
        family=ModelFamily.llama,
        name=ModelName.llama_3_2_90b,
        friendly_name="Llama 3.2 90B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                provider_options={"model": "meta-llama/llama-3.2-90b-vision-instruct"},
            ),
        ],
    ),
    # Phi 3.5
    KilnModel(
        family=ModelFamily.phi,
        name=ModelName.phi_3_5,
        friendly_name="Phi 3.5",
        supports_structured_output=False,
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_structured_output=False,
                provider_options={"model": "phi3.5"},
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "microsoft/phi-3.5-mini-128k-instruct"},
            ),
        ],
    ),
    # Gemma 2 2.6b
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_2_2b,
        friendly_name="Gemma 2 2B",
        supports_structured_output=False,
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_structured_output=False,
                provider_options={
                    "model": "gemma2:2b",
                },
            ),
        ],
    ),
    # Gemma 2 9b
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_2_9b,
        friendly_name="Gemma 2 9B",
        supports_structured_output=False,
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                provider_options={
                    "model": "gemma2:9b",
                },
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "google/gemma-2-9b-it"},
            ),
        ],
    ),
    # Gemma 2 27b
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_2_27b,
        friendly_name="Gemma 2 27B",
        supports_structured_output=False,
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                provider_options={
                    "model": "gemma2:27b",
                },
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                provider_options={"model": "google/gemma-2-27b-it"},
            ),
        ],
    ),
]


def provider_name_from_id(id: str) -> str:
    """
    Converts a provider ID to its human-readable name.

    Args:
        id: The provider identifier string

    Returns:
        The human-readable name of the provider

    Raises:
        ValueError: If the provider ID is invalid or unhandled
    """
    if id in ModelProviderName.__members__:
        enum_id = ModelProviderName(id)
        match enum_id:
            case ModelProviderName.amazon_bedrock:
                return "Amazon Bedrock"
            case ModelProviderName.openrouter:
                return "OpenRouter"
            case ModelProviderName.groq:
                return "Groq"
            case ModelProviderName.ollama:
                return "Ollama"
            case ModelProviderName.openai:
                return "OpenAI"
            case _:
                # triggers pyright warning if I miss a case
                raise_exhaustive_error(enum_id)

    return "Unknown provider: " + id


def raise_exhaustive_error(value: NoReturn) -> NoReturn:
    raise ValueError(f"Unhandled enum value: {value}")


@dataclass
class ModelProviderWarning:
    required_config_keys: List[str]
    message: str


provider_warnings: Dict[ModelProviderName, ModelProviderWarning] = {
    ModelProviderName.amazon_bedrock: ModelProviderWarning(
        required_config_keys=["bedrock_access_key", "bedrock_secret_key"],
        message="Attempted to use Amazon Bedrock without an access key and secret set. \nGet your keys from https://us-west-2.console.aws.amazon.com/bedrock/home?region=us-west-2#/overview",
    ),
    ModelProviderName.openrouter: ModelProviderWarning(
        required_config_keys=["open_router_api_key"],
        message="Attempted to use OpenRouter without an API key set. \nGet your API key from https://openrouter.ai/settings/keys",
    ),
    ModelProviderName.groq: ModelProviderWarning(
        required_config_keys=["groq_api_key"],
        message="Attempted to use Groq without an API key set. \nGet your API key from https://console.groq.com/keys",
    ),
    ModelProviderName.openai: ModelProviderWarning(
        required_config_keys=["open_ai_api_key"],
        message="Attempted to use OpenAI without an API key set. \nGet your API key from https://platform.openai.com/account/api-keys",
    ),
}


def get_config_value(key: str):
    try:
        return Config.shared().__getattr__(key)
    except AttributeError:
        return None


def check_provider_warnings(provider_name: ModelProviderName):
    """
    Validates that required configuration is present for a given provider.

    Args:
        provider_name: The provider to check

    Raises:
        ValueError: If required configuration keys are missing
    """
    warning_check = provider_warnings.get(provider_name)
    if warning_check is None:
        return
    for key in warning_check.required_config_keys:
        if get_config_value(key) is None:
            raise ValueError(warning_check.message)


async def langchain_model_from(
    name: str, provider_name: str | None = None
) -> BaseChatModel:
    """
    Creates a LangChain chat model instance for the specified model and provider.

    Args:
        name: The name of the model to instantiate
        provider_name: Optional specific provider to use (defaults to first available)

    Returns:
        A configured LangChain chat model instance

    Raises:
        ValueError: If the model/provider combination is invalid or misconfigured
    """
    if name not in ModelName.__members__:
        raise ValueError(f"Invalid name: {name}")

    # Select the model from built_in_models using the name
    model = next(filter(lambda m: m.name == name, built_in_models))
    if model is None:
        raise ValueError(f"Model {name} not found")

    # If a provider is provided, select the provider from the model's provider_config
    provider: KilnModelProvider | None = None
    if model.providers is None or len(model.providers) == 0:
        raise ValueError(f"Model {name} has no providers")
    elif provider_name is None:
        # TODO: priority order
        provider = model.providers[0]
    else:
        provider = next(
            filter(lambda p: p.name == provider_name, model.providers), None
        )
    if provider is None:
        raise ValueError(f"Provider {provider_name} not found for model {name}")

    check_provider_warnings(provider.name)

    if provider.name == ModelProviderName.openai:
        api_key = Config.shared().open_ai_api_key
        return ChatOpenAI(**provider.provider_options, openai_api_key=api_key)  # type: ignore[arg-type]
    elif provider.name == ModelProviderName.groq:
        api_key = Config.shared().groq_api_key
        if api_key is None:
            raise ValueError(
                "Attempted to use Groq without an API key set. "
                "Get your API key from https://console.groq.com/keys"
            )
        return ChatGroq(**provider.provider_options, groq_api_key=api_key)  # type: ignore[arg-type]
    elif provider.name == ModelProviderName.amazon_bedrock:
        api_key = Config.shared().bedrock_access_key
        secret_key = Config.shared().bedrock_secret_key
        # langchain doesn't allow passing these, so ugly hack to set env vars
        os.environ["AWS_ACCESS_KEY_ID"] = api_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
        return ChatBedrockConverse(
            **provider.provider_options,
        )
    elif provider.name == ModelProviderName.ollama:
        # Ollama model naming is pretty flexible. We try a few versions of the model name
        potential_model_names = []
        if "model" in provider.provider_options:
            potential_model_names.append(provider.provider_options["model"])
        if "model_aliases" in provider.provider_options:
            potential_model_names.extend(provider.provider_options["model_aliases"])

        # Get the list of models Ollama supports
        ollama_connection = await get_ollama_connection()
        if ollama_connection is None:
            raise ValueError("Failed to connect to Ollama. Ensure Ollama is running.")

        for model_name in potential_model_names:
            if ollama_model_supported(ollama_connection, model_name):
                return ChatOllama(model=model_name, base_url=ollama_base_url())

        raise ValueError(f"Model {name} not installed on Ollama")
    elif provider.name == ModelProviderName.openrouter:
        api_key = Config.shared().open_router_api_key
        base_url = getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
        return ChatOpenAI(
            **provider.provider_options,
            openai_api_key=api_key,  # type: ignore[arg-type]
            openai_api_base=base_url,  # type: ignore[arg-type]
            default_headers={
                "HTTP-Referer": "https://getkiln.ai/openrouter",
                "X-Title": "KilnAI",
            },
        )
    else:
        raise ValueError(f"Invalid model or provider: {name} - {provider_name}")


def ollama_base_url() -> str:
    """
    Gets the base URL for Ollama API connections.

    Returns:
        The base URL to use for Ollama API calls, using environment variable if set
        or falling back to localhost default
    """
    env_base_url = os.getenv("OLLAMA_BASE_URL")
    if env_base_url is not None:
        return env_base_url
    return "http://localhost:11434"


async def ollama_online() -> bool:
    """
    Checks if the Ollama service is available and responding.

    Returns:
        True if Ollama is available and responding, False otherwise
    """
    try:
        httpx.get(ollama_base_url() + "/api/tags")
    except httpx.RequestError:
        return False
    return True


class OllamaConnection(BaseModel):
    message: str
    models: List[str]


# Parse the Ollama /api/tags response
def parse_ollama_tags(tags: Any) -> OllamaConnection | None:
    # Build a list of models we support for Ollama from the built-in model list
    supported_ollama_models = [
        provider.provider_options["model"]
        for model in built_in_models
        for provider in model.providers
        if provider.name == ModelProviderName.ollama
    ]
    # Append model_aliases to supported_ollama_models
    supported_ollama_models.extend(
        [
            alias
            for model in built_in_models
            for provider in model.providers
            for alias in provider.provider_options.get("model_aliases", [])
        ]
    )

    if "models" in tags:
        models = tags["models"]
        if isinstance(models, list):
            model_names = [model["model"] for model in models]
            print(f"model_names: {model_names}")
            available_supported_models = [
                model
                for model in model_names
                if model in supported_ollama_models
                or model in [f"{m}:latest" for m in supported_ollama_models]
            ]
            if available_supported_models:
                return OllamaConnection(
                    message="Ollama connected",
                    models=available_supported_models,
                )

    return OllamaConnection(
        message="Ollama is running, but no supported models are installed. Install one or more supported model, like 'ollama pull phi3.5'.",
        models=[],
    )


async def get_ollama_connection() -> OllamaConnection | None:
    """
    Gets the connection status for Ollama.
    """
    try:
        tags = requests.get(ollama_base_url() + "/api/tags", timeout=5).json()

    except Exception:
        return None

    return parse_ollama_tags(tags)


def ollama_model_supported(conn: OllamaConnection, model_name: str) -> bool:
    return model_name in conn.models or f"{model_name}:latest" in conn.models
