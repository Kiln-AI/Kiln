from typing import List

import httpx
import openai
from pydantic import BaseModel, Field

from kiln_ai.adapters.ml_model_list import ModelProviderName, built_in_models
from kiln_ai.utils.config import Config


def docker_model_runner_base_url() -> str:
    """
    Gets the base URL for Docker Model Runner API connections.

    Returns:
        The base URL to use for Docker Model Runner API calls, using environment variable if set
        or falling back to localhost default
    """
    config_base_url = Config.shared().docker_model_runner_base_url
    if config_base_url:
        return config_base_url
    return "http://localhost:12434/engines/llama.cpp"


async def docker_model_runner_online() -> bool:
    """
    Checks if the Docker Model Runner service is available and responding.

    Returns:
        True if Docker Model Runner is available and responding, False otherwise
    """
    try:
        base_url = docker_model_runner_base_url()
        # Docker Model Runner uses OpenAI-compatible endpoints
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/v1/models", timeout=5.0)
            response.raise_for_status()
    except httpx.RequestError:
        return False
    return True


class DockerModelRunnerConnection(BaseModel):
    message: str
    version: str | None = None
    supported_models: List[str]
    untested_models: List[str] = Field(default_factory=list)

    def all_models(self) -> List[str]:
        return self.supported_models + self.untested_models


# Parse the Docker Model Runner /v1/models response
def parse_docker_model_runner_models(
    models: List[openai.types.Model],
) -> DockerModelRunnerConnection | None:
    # Build a list of models we support for Docker Model Runner from the built-in model list
    supported_docker_models = [
        provider.model_id
        for model in built_in_models
        for provider in model.providers
        if provider.name == ModelProviderName.docker_model_runner
    ]
    # Note: Docker Model Runner aliases will be added when we configure models

    model_names = [model.id for model in models]
    available_supported_models = []
    untested_models = []

    for model_name in model_names:
        if model_name in supported_docker_models:
            available_supported_models.append(model_name)
        else:
            untested_models.append(model_name)

    if available_supported_models or untested_models:
        return DockerModelRunnerConnection(
            message="Docker Model Runner connected",
            supported_models=available_supported_models,
            untested_models=untested_models,
        )

    return DockerModelRunnerConnection(
        message="Docker Model Runner is running, but no supported models are available. Ensure models like 'ai/llama3.2:3B-Q4_K_M', 'ai/qwen3:8B-Q4_K_M', or 'ai/gemma3n:4B-Q4_K_M' are loaded.",
        supported_models=[],
        untested_models=[],
    )


async def get_docker_model_runner_connection(
    custom_url: str | None = None,
) -> DockerModelRunnerConnection | None:
    """
    Gets the connection status for Docker Model Runner.

    Args:
        custom_url: Optional custom URL to use instead of the configured one
    """
    try:
        base_url = custom_url or docker_model_runner_base_url()
        # Use OpenAI client to get models list
        client = openai.OpenAI(
            api_key="dummy",  # Docker Model Runner doesn't require API key
            base_url=f"{base_url}/v1",
            max_retries=0,
        )
        models_response = client.models.list()

    except (openai.APIConnectionError, openai.APIError, httpx.RequestError):
        return None

    return parse_docker_model_runner_models(list(models_response))


def docker_model_runner_model_installed(
    conn: DockerModelRunnerConnection, model_name: str
) -> bool:
    all_models = conn.all_models()
    return model_name in all_models
