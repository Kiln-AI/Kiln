import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List

import litellm
import openai
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from kiln_ai.adapters.ml_model_list import (
    KilnModel,
    KilnModelProvider,
    ModelName,
    ModelProviderName,
    built_in_models,
)
from kiln_ai.adapters.ollama_tools import (
    OllamaConnection,
    ollama_base_url,
    parse_ollama_tags,
)
from kiln_ai.adapters.provider_tools import provider_name_from_id, provider_warnings
from kiln_ai.datamodel.registry import all_projects
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


async def connect_ollama(custom_ollama_url: str | None = None) -> OllamaConnection:
    # Tags is a list of Ollama models. Proves Ollama is running, and models are available.
    if (
        custom_ollama_url
        and not custom_ollama_url.startswith("http://")
        and not custom_ollama_url.startswith("https://")
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid Ollama URL. It must start with http:// or https://",
        )

    try:
        base_url = custom_ollama_url or ollama_base_url()
        tags = requests.get(base_url + "/api/tags", timeout=5).json()
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=417,
            detail="Failed to connect. Ensure Ollama app is running.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to Ollama: {e}",
        )

    ollama_connection = parse_ollama_tags(tags)
    if ollama_connection is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to parse Ollama data - unsure which models are installed.",
        )

    # attempt to get the Ollama version
    try:
        version_body = requests.get(base_url + "/api/version", timeout=5).json()
        ollama_connection.version = version_body.get("version", None)
    except Exception:
        pass

    # Save the custom Ollama URL if used to connect
    if custom_ollama_url and custom_ollama_url != Config.shared().ollama_base_url:
        Config.shared().save_setting("ollama_base_url", custom_ollama_url)

    return ollama_connection


class ModelDetails(BaseModel):
    id: str
    name: str
    supports_structured_output: bool
    supports_data_gen: bool
    supports_logprobs: bool
    # True if this is a untested model (typically user added). We don't know if these support structured output, data gen, etc. They should appear in their own section in the UI.
    untested_model: bool = Field(default=False)
    task_filter: List[str] | None = Field(default=None)


class AvailableModels(BaseModel):
    provider_name: str
    provider_id: str
    models: List[ModelDetails]


class ProviderModel(BaseModel):
    id: str
    name: str


class ProviderModels(BaseModel):
    models: Dict[ModelName, ProviderModel]


def connect_provider_api(app: FastAPI):
    @app.get("/api/providers/models")
    async def get_providers_models() -> ProviderModels:
        models = {}
        for model in built_in_models:
            models[model.name] = ProviderModel(id=model.name, name=model.friendly_name)
        return ProviderModels(models=models)

    # returns map, of provider name to list of model names
    @app.get("/api/available_models")
    async def get_available_models() -> List[AvailableModels]:
        # Providers with just keys can return all their models if keys are set
        key_providers: List[str] = []

        for provider, provider_warning in provider_warnings.items():
            has_keys = True
            for required_key in provider_warning.required_config_keys:
                if Config.shared().get_value(required_key) is None:
                    has_keys = False
                    break
            if has_keys:
                key_providers.append(provider)
        models: List[AvailableModels] = [
            AvailableModels(
                provider_name=provider_name_from_id(provider),
                provider_id=provider,
                models=[],
            )
            for provider in key_providers
        ]

        for model in built_in_models:
            for provider in model.providers:
                if not provider.model_id:
                    # it's possible for models to not have an ID (fine-tune only model)
                    continue
                if provider.name in key_providers:
                    available_models = next(
                        (m for m in models if m.provider_id == provider.name), None
                    )
                    if available_models:
                        available_models.models.append(
                            ModelDetails(
                                id=model.name,
                                name=model.friendly_name,
                                supports_structured_output=provider.supports_structured_output,
                                supports_data_gen=provider.supports_data_gen,
                                supports_logprobs=provider.supports_logprobs,
                            )
                        )

        # Ollama is special: check which models are installed
        ollama_models = await available_ollama_models()
        if ollama_models:
            models.insert(0, ollama_models)

        # Add any fine tuned models
        fine_tuned_models = all_fine_tuned_models()
        if fine_tuned_models:
            models.append(fine_tuned_models)

        # Add any custom models
        custom = custom_models()
        if custom:
            models.append(custom)

        # Add any openai compatible providers
        openai_compatible = openai_compatible_providers()
        models.extend(openai_compatible)

        return models

    @app.get("/api/provider/ollama/connect")
    async def connect_ollama_api(
        custom_ollama_url: str | None = None,
    ) -> OllamaConnection:
        return await connect_ollama(custom_ollama_url)

    @app.post("/api/provider/openai_compatible")
    async def save_openai_compatible_providers(name: str, base_url: str, api_key: str):
        providers = Config.shared().openai_compatible_providers or []
        existing_provider = next((p for p in providers if p["name"] == name), None)
        if existing_provider:
            raise HTTPException(
                status_code=400,
                detail="Provider with this name already exists",
            )
        providers.append(
            {
                "name": name,
                "base_url": base_url,
                "api_key": api_key,
            }
        )
        Config.shared().openai_compatible_providers = providers
        return JSONResponse(
            status_code=200,
            content={"message": "OpenAI compatible provider saved"},
        )

    @app.delete("/api/provider/openai_compatible")
    async def delete_openai_compatible_providers(name: str):
        if not name:
            return JSONResponse(
                status_code=400,
                content={"message": "Name is required"},
            )
        providers = Config.shared().openai_compatible_providers or []
        providers = [p for p in providers if p["name"] != name]
        Config.shared().openai_compatible_providers = providers
        return JSONResponse(
            status_code=200,
            content={"message": "OpenAI compatible provider deleted"},
        )

    def parse_api_key(key_data: dict) -> str:
        return parse_api_field(key_data, "API Key")

    def parse_api_field(key_data: dict, field_name: str) -> str:
        api_key = key_data.get(field_name)
        if not api_key or not isinstance(api_key, str):
            raise HTTPException(
                status_code=400,
                detail=f"{field_name} not found",
            )
        return api_key

    @app.post("/api/provider/connect_api_key")
    async def connect_api_key(payload: dict):
        provider = payload.get("provider")
        key_data = payload.get("key_data")
        if not isinstance(key_data, dict) or not isinstance(provider, str):
            return JSONResponse(
                status_code=400,
                content={"message": "Invalid key_data or provider"},
            )

        # Wandb is not a typical AI provider, but it's a provider you can connect through this UI/API
        if provider == "wandb":
            # Load optional base URL
            base_url = None
            if "Base URL" in key_data:
                base_url = parse_url(key_data, "Base URL")
            return await connect_wandb(
                parse_api_key(key_data),
                base_url,
            )

        if provider not in ModelProviderName.__members__:
            return JSONResponse(
                status_code=400,
                content={"message": f"Provider {provider} not supported"},
            )

        typed_provider = ModelProviderName(provider)

        match typed_provider:
            case ModelProviderName.openai:
                return await connect_openai(parse_api_key(key_data))
            case ModelProviderName.groq:
                return await connect_groq(parse_api_key(key_data))
            case ModelProviderName.openrouter:
                return await connect_openrouter(parse_api_key(key_data))
            case ModelProviderName.fireworks_ai:
                return await connect_fireworks(key_data)
            case ModelProviderName.amazon_bedrock:
                return await connect_bedrock(key_data)
            case ModelProviderName.anthropic:
                return await connect_anthropic(parse_api_key(key_data))
            case ModelProviderName.gemini_api:
                return await connect_gemini(parse_api_key(key_data))
            case ModelProviderName.azure_openai:
                endpoint = parse_url(key_data, "Endpoint URL")
                return await connect_azure_openai(parse_api_key(key_data), endpoint)
            case ModelProviderName.huggingface:
                return await connect_huggingface(parse_api_key(key_data))
            case ModelProviderName.vertex:
                return await connect_vertex(
                    parse_api_field(key_data, "Project ID"),
                    parse_api_field(key_data, "Project Location"),
                )
            case ModelProviderName.together_ai:
                return await connect_together(parse_api_key(key_data))
            case (
                ModelProviderName.kiln_custom_registry
                | ModelProviderName.kiln_fine_tune
                | ModelProviderName.openai_compatible
                | ModelProviderName.ollama
            ):
                return JSONResponse(
                    status_code=400,
                    content={"message": "Provider not supported for API keys"},
                )
            case _:
                raise_exhaustive_enum_error(typed_provider)

    @app.post("/api/provider/disconnect_api_key")
    async def disconnect_api_key(provider_id: str) -> JSONResponse:
        if provider_id == "wandb":
            # Wandb is not an AI provider, but it's a provider you can connect, supported by this UI/API
            Config.shared().wandb_api_key = None
            Config.shared().wandb_base_url = None
        else:
            if provider_id not in ModelProviderName.__members__:
                return JSONResponse(
                    status_code=400,
                    content={"message": f"Invalid provider: {provider_id}"},
                )

            typed_provider_id = ModelProviderName(provider_id)

            match typed_provider_id:
                case ModelProviderName.openai:
                    Config.shared().open_ai_api_key = None
                case ModelProviderName.groq:
                    Config.shared().groq_api_key = None
                case ModelProviderName.openrouter:
                    Config.shared().open_router_api_key = None
                case ModelProviderName.fireworks_ai:
                    Config.shared().fireworks_api_key = None
                    Config.shared().fireworks_account_id = None
                case ModelProviderName.amazon_bedrock:
                    Config.shared().bedrock_access_key = None
                    Config.shared().bedrock_secret_key = None
                case ModelProviderName.anthropic:
                    Config.shared().anthropic_api_key = None
                case ModelProviderName.gemini_api:
                    Config.shared().gemini_api_key = None
                case ModelProviderName.azure_openai:
                    Config.shared().azure_openai_api_key = None
                    Config.shared().azure_openai_endpoint = None
                case ModelProviderName.huggingface:
                    Config.shared().huggingface_api_key = None
                case ModelProviderName.vertex:
                    Config.shared().vertex_project_id = None
                    Config.shared().vertex_location = None
                case ModelProviderName.together_ai:
                    Config.shared().together_api_key = None
                case (
                    ModelProviderName.kiln_custom_registry
                    | ModelProviderName.kiln_fine_tune
                    | ModelProviderName.openai_compatible
                    | ModelProviderName.ollama
                ):
                    return JSONResponse(
                        status_code=400,
                        content={"message": "Provider not supported"},
                    )
                case _:
                    # Raises a pyright error if I miss a case
                    raise_exhaustive_enum_error(typed_provider_id)

        return JSONResponse(
            status_code=200,
            content={"message": "Provider disconnected"},
        )


async def connect_openrouter(key: str):
    try:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        # invalid body, but we just want to see if the key is valid
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={},
        )

        # 401 def means invalid API key
        if response.status_code == 401:
            return JSONResponse(
                status_code=401,
                content={
                    "message": "Failed to connect to OpenRouter. Invalid API key."
                },
            )
        else:
            # No 401 means key is valid (even it it's an error, which we expect with empty body)
            Config.shared().open_router_api_key = key

            return JSONResponse(
                status_code=200,
                content={"message": "Connected to OpenRouter"},
            )
            # Any non-200 status code is an error
    except Exception as e:
        # unexpected error
        return JSONResponse(
            status_code=400,
            content={"message": f"Failed to connect to OpenRouter. Error: {str(e)}"},
        )


async def connect_fireworks(key_data: dict):
    try:
        key = key_data.get("API Key")
        account_id = key_data.get("Account ID")
        if (
            not account_id
            or not isinstance(account_id, str)
            or not key
            or not isinstance(key, str)
        ):
            raise HTTPException(
                status_code=400,
                detail="Account ID or API Key not found",
            )

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        # list the shared models (fireworks account)
        response = requests.get(
            f"https://api.fireworks.ai/v1/accounts/{account_id}/models",
            headers=headers,
        )

        if response.status_code == 403:
            return JSONResponse(
                status_code=401,
                content={
                    "message": "Failed to connect to Fireworks. Invalid API key or Account ID."
                },
            )
        elif response.status_code == 200:
            Config.shared().fireworks_api_key = key
            Config.shared().fireworks_account_id = account_id

            return JSONResponse(
                status_code=200,
                content={"message": "Connected to Fireworks"},
            )
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "message": f"Failed to connect to Fireworks. Error: [{response.status_code}] {response.text}"
                },
            )
    except Exception as e:
        # unexpected error
        return JSONResponse(
            status_code=400,
            content={"message": f"Failed to connect to Fireworks. Error: {str(e)}"},
        )


async def connect_openai(key: str):
    try:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        response = requests.get("https://api.openai.com/v1/models", headers=headers)

        # 401 def means invalid API key, so special case it
        if response.status_code == 401:
            return JSONResponse(
                status_code=401,
                content={"message": "Failed to connect to OpenAI. Invalid API key."},
            )

        # Any non-200 status code is an error
        response.raise_for_status()
        # If the request is successful, the function will continue
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"message": f"Failed to connect to OpenAI. Error: {str(e)}"},
        )

    # It worked! Save the key and return success
    Config.shared().open_ai_api_key = key

    return JSONResponse(
        status_code=200,
        content={"message": "Connected to OpenAI"},
    )


async def connect_groq(key: str):
    try:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        response = requests.get(
            "https://api.groq.com/openai/v1/models", headers=headers
        )

        if "invalid_api_key" in response.text:
            return JSONResponse(
                status_code=401,
                content={"message": "Failed to connect to Groq. Invalid API key."},
            )

        # Any non-200 status code is an error
        response.raise_for_status()
        # If the request is successful, the function will continue
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"message": f"Failed to connect to Groq. Error: {str(e)}"},
        )

    # It worked! Save the key and return success
    Config.shared().groq_api_key = key

    return JSONResponse(
        status_code=200,
        content={"message": "Connected to Groq"},
    )


async def connect_gemini(key: str):
    try:
        response = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
        )

        if "API_KEY_INVALID" in response.text:
            return JSONResponse(
                status_code=401,
                content={"message": "Failed to connect to Gemini. Invalid API key."},
            )
        elif response.status_code != 200:
            return JSONResponse(
                status_code=400,
                content={
                    "message": f"Failed to connect to Gemini. Error: [{response.status_code}]"
                },
            )
        else:
            Config.shared().gemini_api_key = key
            return JSONResponse(
                status_code=200,
                content={"message": "Connected to Gemini"},
            )
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"message": f"Failed to connect to Gemini. Error: {str(e)}"},
        )


async def connect_vertex(project_id: str, project_location: str):
    try:
        await litellm.acompletion(
            model="vertex_ai/gemini-2.0-flash",
            messages=[{"content": "Hello, how are you?", "role": "user"}],
            vertex_project=project_id,
            vertex_location=project_location,
        )

        Config.shared().vertex_project_id = project_id
        Config.shared().vertex_location = project_location

        return JSONResponse(
            status_code=200,
            content={"message": "Connected to Vertex"},
        )
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"message": f"Failed to connect to Vertex. Error: {str(e)}"},
        )


async def connect_together(key: str):
    try:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        response = requests.get(
            "https://api.together.xyz/v1/models",
            headers=headers,
        )

        if response.status_code == 401:
            return JSONResponse(
                status_code=401,
                content={
                    "message": "Failed to connect to Together.ai. Invalid API key."
                },
            )
        else:
            # Any non-401 status code is okay - auth passed. We expect other errors, but we don't care.
            Config.shared().together_api_key = key
            return JSONResponse(
                status_code=200,
                content={"message": "Connected to Together.ai"},
            )
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"message": f"Failed to connect to Together.ai. Error: {str(e)}"},
        )


async def connect_huggingface(key: str):
    try:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        response = requests.get(
            "https://huggingface.co/api/organizations/fake_org_for_auth_test/resource-groups",
            headers=headers,
        )

        if response.status_code == 401:
            return JSONResponse(
                status_code=401,
                content={
                    "message": "Failed to connect to Huggingface. Invalid API key."
                },
            )
        else:
            # Any non-401 status code is okay - auth passed. We expect other errors, but we don't care.
            Config.shared().huggingface_api_key = key
            return JSONResponse(
                status_code=200,
                content={"message": "Connected to Huggingface"},
            )
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"message": f"Failed to connect to Huggingface. Error: {str(e)}"},
        )


async def connect_anthropic(key: str):
    try:
        headers = {
            "x-api-key": key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        response = requests.get("https://api.anthropic.com/v1/models", headers=headers)

        if response.status_code == 401:
            return JSONResponse(
                status_code=401,
                content={"message": "Failed to connect to Anthropic. Invalid API key."},
            )
        elif response.status_code != 200:
            return JSONResponse(
                status_code=400,
                content={
                    "message": f"Failed to connect to Anthropic. Error: [{response.status_code}]"
                },
            )
        else:
            Config.shared().anthropic_api_key = key
            return JSONResponse(
                status_code=200,
                content={"message": "Connected to Anthropic"},
            )
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"message": f"Failed to connect to Anthropic. Error: {str(e)}"},
        )


async def connect_wandb(key: str, base_url: str | None) -> JSONResponse:
    try:
        api_url = base_url or "https://api.wandb.ai"
        headers = {
            "Content-Type": "application/json",
        }
        # Use GraphQL to validate API key with the viewer.id query
        post_args = {
            "query": "query { viewer { id } }",
        }
        response = requests.post(
            f"{api_url}/graphql",
            timeout=5,
            json=post_args,
            headers=headers,
            auth=("api_key", key),
        )

        if response.status_code == 401:
            return JSONResponse(
                status_code=401,
                content={"message": "Failed to connect to W&B. Invalid API key."},
            )

        json = response.json()
        # Check for common error (invalid key returns 200, but viewer is None)
        if (
            "data" in json
            and "viewer" in json["data"]
            and json["data"]["viewer"] is None
        ):
            return JSONResponse(
                status_code=401,
                content={"message": "Failed to connect to W&B. Invalid API key."},
            )

        # Check for valid response
        if (
            "data" in json
            and "viewer" in json["data"]
            and isinstance(json["data"]["viewer"], dict)
            and "id" in json["data"]["viewer"]
        ):
            # Save the credentials if valid
            Config.shared().wandb_api_key = key
            Config.shared().wandb_base_url = base_url

            return JSONResponse(
                status_code=200, content={"message": "Connected to Weights & Biases"}
            )

        # Unknown error
        return JSONResponse(
            status_code=400,
            content={
                "message": f"Failed to connect to W&B. Account request response: {response.text}"
            },
        )

    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"message": f"Failed to connect to W&B. Error: {str(e)}"},
        )


async def connect_azure_openai(key: str, endpoint: str):
    try:
        headers = {
            "api-key": key,
            "Content-Type": "application/json",
        }
        response = requests.get(
            f"{endpoint}/openai/files?api-version=2024-08-01-preview", headers=headers
        )

        if response.status_code == 401:
            return JSONResponse(
                status_code=401,
                content={
                    "message": "Failed to connect to Azure OpenAI. Invalid API key."
                },
            )
        elif response.status_code != 200:
            return JSONResponse(
                status_code=400,
                content={
                    "message": f"Failed to connect to Azure OpenAI. Error: [{response.status_code}]"
                },
            )
        else:
            Config.shared().azure_openai_api_key = key
            Config.shared().azure_openai_endpoint = endpoint
            return JSONResponse(
                status_code=200,
                content={"message": "Connected to Azure OpenAI"},
            )
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"message": f"Failed to connect to Azure OpenAI. Error: {str(e)}"},
        )


async def connect_bedrock(key_data: dict):
    access_key = key_data.get("Access Key")
    secret_key = key_data.get("Secret Key")
    if (
        not access_key
        or not isinstance(access_key, str)
        or not secret_key
        or not isinstance(secret_key, str)
    ):
        raise HTTPException(
            status_code=400,
            detail="Access Key or Secret Key not found",
        )
    try:
        # Test credentials request, but invalid model so we don't use tokens
        await litellm.acompletion(
            model="bedrock/ai21.jamba-1-5-mini-v9999.8888",
            aws_region_name="us-west-2",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            messages=[{"role": "user", "content": "Hello, how are you?"}],
        )
    except Exception as e:
        # Improve error message if it's a confirmed authentication error
        if isinstance(e, litellm.exceptions.AuthenticationError):
            return JSONResponse(
                status_code=401,
                content={
                    "message": "Failed to connect to Bedrock. Invalid credentials."
                },
            )
        # If it's a bad request, it's a valid key (but the model is fake)
        if isinstance(e, litellm.exceptions.BadRequestError):
            Config.shared().bedrock_access_key = access_key
            Config.shared().bedrock_secret_key = secret_key
            return JSONResponse(
                status_code=200,
                content={"message": "Connected to Bedrock"},
            )
        # Unknown error, raise it
        raise e

    return JSONResponse(
        status_code=400,
        content={"message": "Unknown Bedrock Error"},
    )


async def available_ollama_models() -> AvailableModels | None:
    # Try to connect to Ollama, and get the list of installed models
    try:
        ollama_connection = await connect_ollama()
        ollama_models = AvailableModels(
            provider_name=provider_name_from_id(ModelProviderName.ollama),
            provider_id=ModelProviderName.ollama,
            models=[],
        )

        for ollama_model_tag in ollama_connection.supported_models:
            model, ollama_provider = model_from_ollama_tag(ollama_model_tag)
            if model and ollama_provider:
                ollama_models.models.append(
                    ModelDetails(
                        id=model.name,
                        name=model.friendly_name,
                        supports_structured_output=ollama_provider.supports_structured_output,
                        supports_data_gen=ollama_provider.supports_data_gen,
                        supports_logprobs=False,  # Ollama doesn't support logprobs https://github.com/ollama/ollama/issues/2415
                    )
                )
        for ollama_model in ollama_connection.untested_models:
            ollama_models.models.append(
                ModelDetails(
                    id=ollama_model,
                    name=ollama_model,
                    supports_structured_output=False,
                    supports_data_gen=False,
                    supports_logprobs=False,
                    untested_model=True,
                )
            )

        if len(ollama_models.models) > 0:
            return ollama_models

        return None
    except HTTPException:
        # skip ollama if it's not available
        return None


def model_from_ollama_tag(
    tag: str,
) -> tuple[KilnModel | None, KilnModelProvider | None]:
    for model in built_in_models:
        ollama_provider = next(
            (p for p in model.providers if p.name == ModelProviderName.ollama), None
        )
        if not ollama_provider:
            continue

        model_name = ollama_provider.model_id
        if tag in [model_name, f"{model_name}:latest"]:
            return model, ollama_provider
        if ollama_provider.ollama_model_aliases is not None:
            # all aliases (and :latest)
            for alias in ollama_provider.ollama_model_aliases:
                if tag in [alias, f"{alias}:latest"]:
                    return model, ollama_provider

    return None, None


def custom_models() -> AvailableModels | None:
    custom_model_ids = Config.shared().custom_models
    if not custom_model_ids or len(custom_model_ids) == 0:
        return None

    models: List[ModelDetails] = []
    for model_id in custom_model_ids:
        try:
            provider_id = model_id.split("::", 1)[0]
            model_name = model_id.split("::", 1)[1]
            models.append(
                ModelDetails(
                    id=model_id,
                    name=f"{provider_name_from_id(provider_id)}: {model_name}",
                    supports_structured_output=False,
                    supports_data_gen=False,
                    supports_logprobs=False,
                    untested_model=True,
                )
            )
        except Exception:
            # Continue on to the rest
            logger.error("Error processing custom model %s", model_id, exc_info=True)

    return AvailableModels(
        provider_name="Custom Models",
        provider_id=ModelProviderName.kiln_custom_registry,
        models=models,
    )


def all_fine_tuned_models() -> AvailableModels | None:
    # Add any fine tuned models
    models: List[ModelDetails] = []

    for project in all_projects():
        for task in project.tasks():
            for fine_tune in task.finetunes():
                # check if the fine tune is completed
                if fine_tune.fine_tune_model_id:
                    models.append(
                        ModelDetails(
                            id=f"{project.id}::{task.id}::{fine_tune.id}",
                            name=fine_tune.name
                            + f" ({provider_name_from_id(fine_tune.provider)})",
                            # YMMV, but we'll assume all fine tuned models support structured output and data gen
                            supports_structured_output=True,
                            supports_data_gen=True,
                            supports_logprobs=False,
                            task_filter=[str(task.id)],
                        )
                    )

    if len(models) > 0:
        return AvailableModels(
            provider_name="Fine Tuned Models",
            provider_id=ModelProviderName.kiln_fine_tune,
            models=models,
        )
    return None


@dataclass
class OpenAICompatibleProviderCache:
    providers: List[AvailableModels]
    last_updated: datetime | None = None
    openai_compat_config_when_cached: Any | None = None
    had_error: bool = False

    # Cache for 60 minutes, or if the config changes
    def is_stale(self) -> bool:
        if self.last_updated is None:
            return True

        if self.had_error:
            return True

        if datetime.now() - self.last_updated > timedelta(minutes=60):
            return True

        current_providers = Config.shared().openai_compatible_providers
        if current_providers != self.openai_compat_config_when_cached:
            return True

        return False


_openai_compatible_providers_cache: OpenAICompatibleProviderCache | None = None


def openai_compatible_providers() -> List[AvailableModels]:
    global _openai_compatible_providers_cache

    if (
        _openai_compatible_providers_cache is None
        or _openai_compatible_providers_cache.is_stale()
    ):
        # Load values and cache them
        cache = openai_compatible_providers_load_cache()
        _openai_compatible_providers_cache = cache

    if _openai_compatible_providers_cache is None:
        return []

    return _openai_compatible_providers_cache.providers


def openai_compatible_providers_load_cache() -> OpenAICompatibleProviderCache | None:
    provider_config = Config.shared().openai_compatible_providers
    if not provider_config or len(provider_config) == 0:
        return None

    # Errors that can be retried, like network issues, are tracked in cache.
    # We retry populating the cache on each call
    has_error = False

    openai_compatible_models: List[AvailableModels] = []
    for provider in provider_config:
        models: List[ModelDetails] = []
        base_url = provider.get("base_url")
        if not base_url or not base_url.startswith("http"):
            logger.warning(
                "No base URL for OpenAI compatible provider %s - %s", provider, base_url
            )
            continue
        name = provider.get("name")
        if not name:
            logger.warning("No name for OpenAI compatible provider %s", provider)
            continue

        # API key is optional, as some providers don't require it
        api_key = provider.get("api_key") or ""
        openai_client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            # Important: max_retries must be 0 for performance.
            # It's common for these servers to be down sometimes (could be local app that isn't running)
            # OpenAI client will retry a few times, with a sleep in between! Big loading perf hit.
            max_retries=0,
        )

        try:
            provider_models = openai_client.models.list()
            for model in provider_models:
                models.append(
                    ModelDetails(
                        id=f"{name}::{model.id}",
                        name=model.id,
                        supports_structured_output=False,
                        supports_data_gen=False,
                        supports_logprobs=False,
                        untested_model=True,
                    )
                )

            openai_compatible_models.append(
                AvailableModels(
                    provider_id=ModelProviderName.openai_compatible,
                    provider_name=name,
                    models=models,
                )
            )
        except Exception:
            logger.error(
                "Error connecting to OpenAI compatible provider %s", name, exc_info=True
            )
            has_error = True
            continue

    cache = OpenAICompatibleProviderCache(
        providers=openai_compatible_models,
        last_updated=datetime.now(),
        openai_compat_config_when_cached=provider_config,
        had_error=has_error,
    )

    return cache


def parse_url(key_data: dict, field_name: str) -> str:
    url = key_data.get(field_name)
    if not url or not isinstance(url, str):
        raise HTTPException(
            status_code=400,
            detail="Endpoint URL not found",
        )
    if url.endswith("/"):
        # remove last slash
        url = url[:-1]
    if not url.startswith("http"):
        raise HTTPException(
            status_code=400,
            detail="Endpoint URL must start with http or https",
        )
    return url
