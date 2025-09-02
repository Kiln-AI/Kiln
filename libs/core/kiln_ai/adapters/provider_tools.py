import logging
from dataclasses import dataclass
from typing import Dict, List

from kiln_ai.adapters.docker_model_runner_tools import (
    get_docker_model_runner_connection,
)
from kiln_ai.adapters.ml_model_list import (
    KilnModel,
    KilnModelProvider,
    ModelParserID,
    ModelProviderName,
    StructuredOutputMode,
    built_in_models,
)
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.adapters.ollama_tools import get_ollama_connection
from kiln_ai.datamodel import Finetune, Task
from kiln_ai.datamodel.datamodel_enums import ChatStrategy
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_ai.utils.project_utils import project_from_id

logger = logging.getLogger(__name__)


async def provider_enabled(provider_name: ModelProviderName) -> bool:
    if provider_name == ModelProviderName.ollama:
        try:
            conn = await get_ollama_connection()
            return conn is not None and (
                len(conn.supported_models) > 0 or len(conn.untested_models) > 0
            )
        except Exception:
            return False

    if provider_name == ModelProviderName.docker_model_runner:
        try:
            conn = await get_docker_model_runner_connection()
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


def builtin_model_from(
    name: str, provider_name: str | None = None
) -> KilnModelProvider | None:
    """
    Gets a model provider from the built-in list of models.

    Args:
        name: The name of the model to get
        provider_name: Optional specific provider to use (defaults to first available)

    Returns:
        A KilnModelProvider, or None if not found
    """
    # Select the model from built_in_models using the name
    model = next(filter(lambda m: m.name == name, built_in_models), None)
    if model is None:
        return None

    # If a provider is provided, select the appropriate provider. Otherwise, use the first available.
    provider: KilnModelProvider | None = None
    if model.providers is None or len(model.providers) == 0:
        return None
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


def core_provider(model_id: str, provider_name: ModelProviderName) -> ModelProviderName:
    """
    Get the provider that should be run.

    Some provider IDs are wrappers (fine-tunes, custom models). This maps these to runnable providers (openai, ollama, etc)
    """

    # Custom models map to the underlying provider
    if provider_name is ModelProviderName.kiln_custom_registry:
        provider_name, _ = parse_custom_model_id(model_id)
        return provider_name

    # Fine-tune provider maps to an underlying provider
    if provider_name is ModelProviderName.kiln_fine_tune:
        finetune = finetune_from_id(model_id)
        if finetune.provider not in ModelProviderName.__members__:
            raise ValueError(
                f"Finetune {model_id} has no underlying provider {finetune.provider}"
            )
        return ModelProviderName(finetune.provider)

    return provider_name


def parse_custom_model_id(
    model_id: str,
) -> tuple[ModelProviderName, str]:
    if "::" not in model_id:
        raise ValueError(f"Invalid custom model ID: {model_id}")

    # For custom registry, get the provider name and model name from the model id
    provider_name = model_id.split("::", 1)[0]
    model_name = model_id.split("::", 1)[1]

    if provider_name not in ModelProviderName.__members__:
        raise ValueError(f"Invalid provider name: {provider_name}")

    return ModelProviderName(provider_name), model_name


def kiln_model_provider_from(
    name: str, provider_name: str | None = None
) -> KilnModelProvider:
    if provider_name == ModelProviderName.kiln_fine_tune:
        return finetune_provider_model(name)

    if provider_name == ModelProviderName.openai_compatible:
        return lite_llm_provider_model(name)

    built_in_model = builtin_model_from(name, provider_name)
    if built_in_model:
        return built_in_model

    # For custom registry, get the provider name and model name from the model id
    if provider_name == ModelProviderName.kiln_custom_registry:
        provider_name, name = parse_custom_model_id(name)
    else:
        logger.warning(
            f"Unexpected model/provider pair. Will treat as custom model but check your model settings. Provider: {provider_name}/{name}"
        )

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
        model_id=name,
        # We don't know the structured output mode for custom models, so we default to json_instructions which is the only one that works everywhere.
        structured_output_mode=StructuredOutputMode.json_instructions,
    )


def lite_llm_config_for_openai_compatible(
    run_config_properties: RunConfigProperties,
) -> LiteLlmConfig:
    model_id = run_config_properties.model_name
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

    # API key optional - some providers like Ollama don't use it, but LiteLLM errors without one
    api_key = provider.get("api_key") or "NA"
    base_url = provider.get("base_url")
    if base_url is None:
        raise ValueError(
            f"OpenAI compatible provider {openai_provider_name} has no base URL"
        )

    # Update a copy of the run config properties to use the openai compatible provider
    updated_run_config_properties = run_config_properties.model_copy(deep=True)
    updated_run_config_properties.model_provider_name = (
        ModelProviderName.openai_compatible
    )
    updated_run_config_properties.model_name = model_id

    return LiteLlmConfig(
        # OpenAI compatible, with a custom base URL
        run_config_properties=updated_run_config_properties,
        base_url=base_url,
        additional_body_options={
            "api_key": api_key,
        },
    )


def lite_llm_provider_model(
    model_id: str,
) -> KilnModelProvider:
    return KilnModelProvider(
        name=ModelProviderName.openai_compatible,
        model_id=model_id,
        supports_structured_output=False,
        supports_data_gen=False,
        untested_model=True,
    )


finetune_cache: dict[str, Finetune] = {}


def finetune_from_id(model_id: str) -> Finetune:
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

    finetune_cache[model_id] = fine_tune
    return fine_tune


def parser_from_data_strategy(
    data_strategy: ChatStrategy,
) -> ModelParserID | None:
    if data_strategy == ChatStrategy.single_turn_r1_thinking:
        return ModelParserID.r1_thinking
    return None


def finetune_provider_model(
    model_id: str,
) -> KilnModelProvider:
    fine_tune = finetune_from_id(model_id)

    provider = ModelProviderName[fine_tune.provider]
    model_provider = KilnModelProvider(
        name=provider,
        model_id=fine_tune.fine_tune_model_id,
        parser=parser_from_data_strategy(fine_tune.data_strategy),
        reasoning_capable=(
            fine_tune.data_strategy
            in [
                ChatStrategy.single_turn_r1_thinking,
            ]
        ),
        tuned_chat_strategy=fine_tune.data_strategy,
    )

    if provider == ModelProviderName.vertex and fine_tune.fine_tune_model_id:
        # Vertex AI trick: use the model_id "openai/endpoint_id". OpenAI calls the openai compatible API, which supports endpoint.
        # Context: vertex has at least 3 APIS: vertex, openai compatible, and gemini. LiteLLM tries to infer which to use. This works
        # on current LiteLLM version. Could also set base_model to gemini to tell it which to use, but same result.
        endpoint_id = fine_tune.fine_tune_model_id.split("/")[-1]
        model_provider.model_id = f"openai/{endpoint_id}"

    if fine_tune.structured_output_mode is not None:
        # If we know the model was trained with specific output mode, set it
        model_provider.structured_output_mode = fine_tune.structured_output_mode
    else:
        # Some early adopters won't have structured_output_mode set on their fine-tunes.
        # We know that OpenAI uses json_schema, and Fireworks (only other provider) use json_mode.
        # This can be removed in the future
        if provider == ModelProviderName.openai:
            model_provider.structured_output_mode = StructuredOutputMode.json_schema
        else:
            model_provider.structured_output_mode = StructuredOutputMode.json_mode

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
            case ModelProviderName.azure_openai:
                return "Azure OpenAI"
            case ModelProviderName.gemini_api:
                return "Gemini API"
            case ModelProviderName.anthropic:
                return "Anthropic"
            case ModelProviderName.huggingface:
                return "Hugging Face"
            case ModelProviderName.vertex:
                return "Google Vertex AI"
            case ModelProviderName.together_ai:
                return "Together AI"
            case ModelProviderName.siliconflow_cn:
                return "SiliconFlow"
            case ModelProviderName.cerebras:
                return "Cerebras"
            case ModelProviderName.docker_model_runner:
                return "Docker Model Runner"
            case _:
                # triggers pyright warning if I miss a case
                raise_exhaustive_enum_error(enum_id)

    return "Unknown provider: " + id


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
    ModelProviderName.anthropic: ModelProviderWarning(
        required_config_keys=["anthropic_api_key"],
        message="Attempted to use Anthropic without an API key set. \nGet your API key from https://console.anthropic.com/settings/keys",
    ),
    ModelProviderName.gemini_api: ModelProviderWarning(
        required_config_keys=["gemini_api_key"],
        message="Attempted to use Gemini without an API key set. \nGet your API key from https://aistudio.google.com/app/apikey",
    ),
    ModelProviderName.azure_openai: ModelProviderWarning(
        required_config_keys=["azure_openai_api_key", "azure_openai_endpoint"],
        message="Attempted to use Azure OpenAI without an API key and endpoint set. Configure these in settings.",
    ),
    ModelProviderName.huggingface: ModelProviderWarning(
        required_config_keys=["huggingface_api_key"],
        message="Attempted to use Hugging Face without an API key set. \nGet your API key from https://huggingface.co/settings/tokens",
    ),
    ModelProviderName.vertex: ModelProviderWarning(
        required_config_keys=["vertex_project_id"],
        message="Attempted to use Vertex without a project ID set. \nGet your project ID from the Vertex AI console.",
    ),
    ModelProviderName.together_ai: ModelProviderWarning(
        required_config_keys=["together_api_key"],
        message="Attempted to use Together without an API key set. \nGet your API key from https://together.ai/settings/keys",
    ),
    ModelProviderName.siliconflow_cn: ModelProviderWarning(
        required_config_keys=["siliconflow_cn_api_key"],
        message="Attempted to use SiliconFlow without an API key set. \nGet your API key from https://cloud.siliconflow.cn/account/ak",
    ),
    ModelProviderName.cerebras: ModelProviderWarning(
        required_config_keys=["cerebras_api_key"],
        message="Attempted to use Cerebras without an API key set. \nGet your API key from https://cloud.cerebras.ai/platform",
    ),
}
