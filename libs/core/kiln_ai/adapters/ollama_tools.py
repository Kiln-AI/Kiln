import logging
from typing import Any, List

import httpx
import requests
from pydantic import BaseModel, Field

from kiln_ai.adapters.ml_embedding_model_list import built_in_embedding_models
from kiln_ai.adapters.ml_model_list import ModelProviderName, built_in_models
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)


def ollama_base_url() -> str:
    """
    Gets the base URL for Ollama API connections.

    Returns:
        The base URL to use for Ollama API calls, using environment variable if set
        or falling back to localhost default
    """
    config_base_url = Config.shared().ollama_base_url
    if config_base_url:
        return config_base_url
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
    version: str | None = None
    supported_models: List[str]
    untested_models: List[str] = Field(default_factory=list)
    supported_embedding_models: List[str] = Field(default_factory=list)

    def all_models(self) -> List[str]:
        return self.supported_models + self.untested_models

    def all_embedding_models(self) -> List[str]:
        return self.supported_embedding_models


# Parse the Ollama /api/tags response
def parse_ollama_tags(tags: Any) -> OllamaConnection:
    # Build a list of models we support for Ollama from the built-in model list
    supported_ollama_models = set(
        [
            provider.model_id
            for model in built_in_models
            for provider in model.providers
            if provider.name == ModelProviderName.ollama
        ]
    )
    # Append model_aliases to supported_ollama_models
    supported_ollama_models.update(
        [
            alias
            for model in built_in_models
            for provider in model.providers
            for alias in provider.ollama_model_aliases or []
        ]
    )

    supported_ollama_embedding_models = set(
        [
            provider.model_id
            for model in built_in_embedding_models
            for provider in model.providers
            if provider.name == ModelProviderName.ollama
        ]
    )
    supported_ollama_embedding_models.update(
        [
            alias
            for model in built_in_embedding_models
            for provider in model.providers
            for alias in provider.ollama_model_aliases or []
        ]
    )

    if "models" in tags:
        models = tags["models"]
        if isinstance(models, list):
            model_names = [model["model"] for model in models]
            available_supported_models = []
            untested_models = []
            supported_models_latest_aliases = set(
                [f"{m}:latest" for m in supported_ollama_models]
            )
            supported_embedding_models_latest_aliases = set(
                [f"{m}:latest" for m in supported_ollama_embedding_models]
            )

            for model in model_names:
                # Skip embedding models - they should only appear in supported_embedding_models
                if (
                    model in supported_ollama_embedding_models
                    or model in supported_embedding_models_latest_aliases
                ):
                    continue

                if (
                    model in supported_ollama_models
                    or model in supported_models_latest_aliases
                ):
                    available_supported_models.append(model)
                else:
                    untested_models.append(model)

            available_supported_embedding_models = []
            for model in model_names:
                if (
                    model in supported_ollama_embedding_models
                    or model in supported_embedding_models_latest_aliases
                ):
                    available_supported_embedding_models.append(model)

            if (
                available_supported_models
                or untested_models
                or available_supported_embedding_models
            ):
                return OllamaConnection(
                    message="Ollama connected",
                    supported_models=available_supported_models,
                    untested_models=untested_models,
                    supported_embedding_models=available_supported_embedding_models,
                )

    return OllamaConnection(
        message="Ollama is running, but no supported models are installed. Install one or more supported model, like 'ollama pull phi3.5'.",
        supported_models=[],
        untested_models=[],
        supported_embedding_models=[],
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


def ollama_model_installed(conn: OllamaConnection, model_name: str) -> bool:
    all_models = conn.all_models()
    return model_name in all_models or f"{model_name}:latest" in all_models


def ollama_embedding_model_installed(conn: OllamaConnection, model_name: str) -> bool:
    all_embedding_models = conn.all_embedding_models()
    return (
        model_name in all_embedding_models
        or f"{model_name}:latest" in all_embedding_models
    )


def resolve_ollama_model_variant(model_id: str, model_aliases: list[str] | None) -> str:
    """
    Determines which variant of an Ollama model is actually installed - different slugs
    may point to the same underlying model via aliases.

    Checks the primary model_id first, then each alias, and returns the first match.
    If none are installed, returns the original model_id (so error messages are clear).

    Returns:
        The model variant that is installed, or the original model_id if none found
    """
    try:
        tags_response = requests.get(ollama_base_url() + "/api/tags", timeout=5)
        if tags_response.status_code != 200:
            return model_id

        tags = tags_response.json()
        if "models" not in tags or not isinstance(tags["models"], list):
            return model_id

        installed_models = {model["model"] for model in tags["models"]}

        # check model_id (with and without :latest tag)
        if model_id in installed_models or f"{model_id}:latest" in installed_models:
            return model_id

        # check each alias
        if model_aliases:
            for alias in model_aliases:
                if alias in installed_models or f"{alias}:latest" in installed_models:
                    return alias

    except Exception:
        logger.error(f"Error resolving Ollama model variant: {model_id}", exc_info=True)

    return model_id
