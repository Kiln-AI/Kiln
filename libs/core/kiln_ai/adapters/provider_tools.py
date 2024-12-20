from dataclasses import dataclass
from typing import Dict, List, NoReturn

from kiln_ai.adapters.ml_model_list import (
    KilnModel,
    KilnModelProvider,
    ModelName,
    ModelProviderName,
    built_in_models,
)
from kiln_ai.adapters.ollama_tools import (
    get_ollama_connection,
)
from kiln_ai.datamodel import Finetune, Task
from kiln_ai.datamodel.registry import project_from_id

from ..utils.config import Config


async def provider_enabled(provider_name: ModelProviderName) -> bool:
    if provider_name == ModelProviderName.ollama:
        try:
            conn = await get_ollama_connection()
            return conn is not None and (
                len(conn.supported_models) > 0 or len(conn.untested_models) > 0
            )
        except Exception:
            return False

    provider_warning = provider_warnings.get(provider_name)
    if provider_warning is None:
        return False
    for required_key in provider_warning.required_config_keys:
        if get_config_value(required_key) is None:
            return False
    return True


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


async def builtin_model_from(
    name: str, provider_name: str | None = None
) -> KilnModelProvider | None:
    """
    Gets a model and provider from the built-in list of models.

    Args:
        name: The name of the model to get
        provider_name: Optional specific provider to use (defaults to first available)

    Returns:
        A tuple of (provider, model)

    Raises:
        ValueError: If the model or provider is not found, or if the provider is misconfigured
    """
    if name not in ModelName.__members__:
        return None

    # Select the model from built_in_models using the name
    model = next(filter(lambda m: m.name == name, built_in_models))
    if model is None:
        raise ValueError(f"Model {name} not found")

    # If a provider is provided, select the provider from the model's provider_config
    provider: KilnModelProvider | None = None
    if model.providers is None or len(model.providers) == 0:
        raise ValueError(f"Model {name} has no providers")
    elif provider_name is None:
        provider = model.providers[0]
    else:
        provider = next(
            filter(lambda p: p.name == provider_name, model.providers), None
        )
    if provider is None:
        return None

    check_provider_warnings(provider.name)
    return provider


async def kiln_model_provider_from(
    name: str, provider_name: str | None = None
) -> KilnModelProvider:
    if provider_name == ModelProviderName.kiln_fine_tune:
        return finetune_provider_model(name)

    if provider_name == ModelProviderName.openai_compatible:
        return openai_compatible_provider_model(name)

    built_in_model = await builtin_model_from(name, provider_name)
    if built_in_model:
        return built_in_model

    # For custom registry, get the provider name and model name from the model id
    if provider_name == ModelProviderName.kiln_custom_registry:
        provider_name = name.split("::", 1)[0]
        name = name.split("::", 1)[1]

    # Custom/untested model. Set untested, and build a ModelProvider at runtime
    if provider_name is None:
        raise ValueError("Provider name is required for custom models")
    if provider_name not in ModelProviderName.__members__:
        raise ValueError(f"Invalid provider name: {provider_name}")
    provider = ModelProviderName(provider_name)
    check_provider_warnings(provider)
    return KilnModelProvider(
        name=provider,
        supports_structured_output=False,
        supports_data_gen=False,
        untested_model=True,
        provider_options=provider_options_for_custom_model(name, provider_name),
    )


finetune_cache: dict[str, KilnModelProvider] = {}


def openai_compatible_provider_model(
    model_id: str,
) -> KilnModelProvider:
    try:
        openai_provider_name, model_id = model_id.split("::")
    except Exception:
        raise ValueError(f"Invalid openai compatible model ID: {model_id}")

    openai_compatible_providers = Config.shared().openai_compatible_providers or []
    provider = next(
        filter(
            lambda p: p.get("name") == openai_provider_name, openai_compatible_providers
        ),
        None,
    )
    if provider is None:
        raise ValueError(f"OpenAI compatible provider {openai_provider_name} not found")

    # API key optional some providers don't use it
    api_key = provider.get("api_key")
    base_url = provider.get("base_url")
    if base_url is None:
        raise ValueError(
            f"OpenAI compatible provider {openai_provider_name} has no base URL"
        )

    return KilnModelProvider(
        name=ModelProviderName.openai_compatible,
        provider_options={
            "model": model_id,
            "api_key": api_key,
            "openai_api_base": base_url,
        },
        supports_structured_output=False,
        supports_data_gen=False,
        untested_model=True,
    )


def finetune_provider_model(
    model_id: str,
) -> KilnModelProvider:
    if model_id in finetune_cache:
        return finetune_cache[model_id]

    try:
        project_id, task_id, fine_tune_id = model_id.split("::")
    except Exception:
        raise ValueError(f"Invalid fine tune ID: {model_id}")
    project = project_from_id(project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found")
    task = Task.from_id_and_parent_path(task_id, project.path)
    if task is None:
        raise ValueError(f"Task {task_id} not found")
    fine_tune = Finetune.from_id_and_parent_path(fine_tune_id, task.path)
    if fine_tune is None:
        raise ValueError(f"Fine tune {fine_tune_id} not found")
    if fine_tune.fine_tune_model_id is None:
        raise ValueError(
            f"Fine tune {fine_tune_id} not completed. Refresh it's status in the fine-tune tab."
        )

    provider = ModelProviderName[fine_tune.provider]
    model_provider = KilnModelProvider(
        name=provider,
        provider_options={
            "model": fine_tune.fine_tune_model_id,
        },
    )

    # TODO: Don't love this abstraction/logic.
    if fine_tune.provider == ModelProviderName.fireworks_ai:
        # Fireworks finetunes are trained with json, not tool calling (which is LC default format)
        model_provider.adapter_options = {
            "langchain": {
                "with_structured_output_options": {
                    "method": "json_mode",
                }
            }
        }

    finetune_cache[model_id] = model_provider
    return model_provider


def get_model_and_provider(
    model_name: str, provider_name: str
) -> tuple[KilnModel | None, KilnModelProvider | None]:
    model = next(filter(lambda m: m.name == model_name, built_in_models), None)
    if model is None:
        return None, None
    provider = next(filter(lambda p: p.name == provider_name, model.providers), None)
    # all or nothing
    if provider is None or model is None:
        return None, None
    return model, provider


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
            case ModelProviderName.kiln_fine_tune:
                return "Fine Tuned Models"
            case ModelProviderName.fireworks_ai:
                return "Fireworks AI"
            case ModelProviderName.kiln_custom_registry:
                return "Custom Models"
            case ModelProviderName.openai_compatible:
                return "OpenAI Compatible"
            case _:
                # triggers pyright warning if I miss a case
                raise_exhaustive_error(enum_id)

    return "Unknown provider: " + id


def provider_options_for_custom_model(
    model_name: str, provider_name: str
) -> Dict[str, str]:
    """
    Generated model provider options for a custom model. Each has their own format/options.
    """

    if provider_name not in ModelProviderName.__members__:
        raise ValueError(f"Invalid provider name: {provider_name}")

    enum_id = ModelProviderName(provider_name)
    match enum_id:
        case ModelProviderName.amazon_bedrock:
            # us-west-2 is the only region consistently supported by Bedrock
            return {"model": model_name, "region_name": "us-west-2"}
        case (
            ModelProviderName.openai
            | ModelProviderName.ollama
            | ModelProviderName.fireworks_ai
            | ModelProviderName.openrouter
            | ModelProviderName.groq
        ):
            return {"model": model_name}
        case ModelProviderName.kiln_custom_registry:
            raise ValueError(
                "Custom models from registry should be parsed into provider/model before calling this."
            )
        case ModelProviderName.kiln_fine_tune:
            raise ValueError(
                "Fine tuned models should populate provider options via another path"
            )
        case ModelProviderName.openai_compatible:
            raise ValueError(
                "OpenAI compatible models should populate provider options via another path"
            )
        case _:
            # triggers pyright warning if I miss a case
            raise_exhaustive_error(enum_id)

    # Won't reach this, type checking will catch missed values
    return {"model": model_name}


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
    ModelProviderName.fireworks_ai: ModelProviderWarning(
        required_config_keys=["fireworks_api_key", "fireworks_account_id"],
        message="Attempted to use Fireworks without an API key and account ID set. \nGet your API key from https://fireworks.ai/account/api-keys and your account ID from https://fireworks.ai/account/profile",
    ),
}
