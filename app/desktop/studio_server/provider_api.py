import os
from typing import Dict, List

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
from kiln_ai.adapters.provider_tools import (
    provider_name_from_id,
    provider_warnings,
)
from kiln_ai.datamodel.registry import all_projects
from kiln_ai.utils.config import Config
from langchain_aws import ChatBedrockConverse
from pydantic import BaseModel, Field


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

    # Save the custom Ollama URL if used to connect
    if custom_ollama_url and custom_ollama_url != Config.shared().ollama_base_url:
        Config.shared().save_setting("ollama_base_url", custom_ollama_url)

    return ollama_connection


class ModelDetails(BaseModel):
    id: str
    name: str
    supports_structured_output: bool
    supports_data_gen: bool
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

        return models

    @app.get("/api/provider/ollama/connect")
    async def connect_ollama_api(
        custom_ollama_url: str | None = None,
    ) -> OllamaConnection:
        return await connect_ollama(custom_ollama_url)

    @app.post("/api/provider/connect_api_key")
    async def connect_api_key(payload: dict):
        provider = payload.get("provider")
        key_data = payload.get("key_data")
        if not isinstance(key_data, dict) or not isinstance(provider, str):
            return JSONResponse(
                status_code=400,
                content={"message": "Invalid key_data or provider"},
            )

        api_key_providers = ["openai", "groq", "bedrock", "openrouter", "fireworks_ai"]
        if provider not in api_key_providers:
            return JSONResponse(
                status_code=400,
                content={"message": f"Provider {provider} not supported"},
            )

        if provider == "openai" and isinstance(key_data["API Key"], str):
            return await connect_openai(key_data["API Key"])
        elif provider == "groq" and isinstance(key_data["API Key"], str):
            return await connect_groq(key_data["API Key"])
        elif provider == "openrouter" and isinstance(key_data["API Key"], str):
            return await connect_openrouter(key_data["API Key"])
        elif (
            provider == "fireworks_ai"
            and isinstance(key_data["API Key"], str)
            and isinstance(key_data["Account ID"], str)
        ):
            return await connect_fireworks(key_data["API Key"], key_data["Account ID"])
        elif (
            provider == "bedrock"
            and isinstance(key_data["Access Key"], str)
            and isinstance(key_data["Secret Key"], str)
        ):
            return await connect_bedrock(key_data["Access Key"], key_data["Secret Key"])
        else:
            return JSONResponse(
                status_code=400,
                content={"message": f"Provider {provider} missing API key"},
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


async def connect_fireworks(key: str, account_id: str):
    try:
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


async def connect_bedrock(access_key: str, secret_key: str):
    try:
        # Langchain API is not good... need to use env vars. Pop these in finally block
        os.environ["AWS_ACCESS_KEY_ID"] = access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key

        # Fake model, but will get a credential error before AWS realizes it's wrong
        # Ensures we don't spend money on a test call
        llm = ChatBedrockConverse(
            model="fake_model",
            region_name="us-west-2",
        )
        llm.invoke("Hello, how are you?")
    except Exception as e:
        # Check for specific error messages indicating invalid credentials
        if "UnrecognizedClientException" in str(
            e
        ) or "InvalidSignatureException" in str(e):
            return JSONResponse(
                status_code=401,
                content={
                    "message": "Failed to connect to Bedrock. Invalid credentials."
                },
            )
        else:
            # We still expect an error (fake model), but not for invalid credentials which means success!
            Config.shared().bedrock_access_key = access_key
            Config.shared().bedrock_secret_key = secret_key
            return JSONResponse(
                status_code=200,
                content={"message": "Connected to Bedrock"},
            )

    finally:
        os.environ.pop("AWS_ACCESS_KEY_ID")
        os.environ.pop("AWS_SECRET_ACCESS_KEY")

    # we shouldn't get here, but if we do, something went wrong
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
                    )
                )
        for ollama_model in ollama_connection.untested_models:
            ollama_models.models.append(
                ModelDetails(
                    id=ollama_model,
                    name=ollama_model,
                    supports_structured_output=False,
                    supports_data_gen=False,
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

        if "model" in ollama_provider.provider_options:
            model_name = ollama_provider.provider_options["model"]
            if tag in [model_name, f"{model_name}:latest"]:
                return model, ollama_provider
        if "model_aliases" in ollama_provider.provider_options:
            # all aliases (and :latest)
            for alias in ollama_provider.provider_options["model_aliases"]:
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
                    untested_model=True,
                )
            )
        except Exception as e:
            # Continue on to the rest
            print(f"Error processing custom model {model_id}: {e}")

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
