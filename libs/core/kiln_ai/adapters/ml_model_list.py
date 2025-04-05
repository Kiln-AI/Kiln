from enum import Enum
from typing import Dict, List, Literal

from pydantic import BaseModel

from kiln_ai.datamodel import StructuredOutputMode

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
    fireworks_ai = "fireworks_ai"
    kiln_fine_tune = "kiln_fine_tune"
    kiln_custom_registry = "kiln_custom_registry"
    openai_compatible = "openai_compatible"
    anthropic = "anthropic"
    gemini_api = "gemini_api"
    azure_openai = "azure_openai"
    huggingface = "huggingface"
    vertex = "vertex"
    together_ai = "together_ai"


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
    mixtral = "mixtral"
    qwen = "qwen"
    deepseek = "deepseek"
    dolphin = "dolphin"
    grok = "grok"


# Where models have instruct and raw versions, instruct is default and raw is specified
class ModelName(str, Enum):
    """
    Enumeration of specific model versions supported by the system.
    Where models have instruct and raw versions, instruct is default and raw is specified.
    """

    llama_3_1_8b = "llama_3_1_8b"
    llama_3_1_70b = "llama_3_1_70b"
    llama_3_1_405b = "llama_3_1_405b"
    llama_3_2_1b = "llama_3_2_1b"
    llama_3_2_3b = "llama_3_2_3b"
    llama_3_2_11b = "llama_3_2_11b"
    llama_3_2_90b = "llama_3_2_90b"
    llama_3_3_70b = "llama_3_3_70b"
    gpt_4o_mini = "gpt_4o_mini"
    gpt_4o = "gpt_4o"
    gpt_o1_low = "gpt_o1_low"
    gpt_o1_medium = "gpt_o1_medium"
    gpt_o1_high = "gpt_o1_high"
    gpt_o3_mini_low = "gpt_o3_mini_low"
    gpt_o3_mini_medium = "gpt_o3_mini_medium"
    gpt_o3_mini_high = "gpt_o3_mini_high"
    phi_3_5 = "phi_3_5"
    phi_4 = "phi_4"
    phi_4_5p6b = "phi_4_5p6b"
    phi_4_mini = "phi_4_mini"
    mistral_large = "mistral_large"
    mistral_nemo = "mistral_nemo"
    gemma_2_2b = "gemma_2_2b"
    gemma_2_9b = "gemma_2_9b"
    gemma_2_27b = "gemma_2_27b"
    gemma_3_1b = "gemma_3_1b"
    gemma_3_4b = "gemma_3_4b"
    gemma_3_12b = "gemma_3_12b"
    gemma_3_27b = "gemma_3_27b"
    claude_3_5_haiku = "claude_3_5_haiku"
    claude_3_5_sonnet = "claude_3_5_sonnet"
    claude_3_7_sonnet = "claude_3_7_sonnet"
    claude_3_7_sonnet_thinking = "claude_3_7_sonnet_thinking"
    gemini_1_5_flash = "gemini_1_5_flash"
    gemini_1_5_flash_8b = "gemini_1_5_flash_8b"
    gemini_1_5_pro = "gemini_1_5_pro"
    gemini_2_0_flash = "gemini_2_0_flash"
    nemotron_70b = "nemotron_70b"
    mixtral_8x7b = "mixtral_8x7b"
    qwen_2p5_7b = "qwen_2p5_7b"
    qwen_2p5_14b = "qwen_2p5_14b"
    qwen_2p5_72b = "qwen_2p5_72b"
    qwq_32b = "qwq_32b"
    deepseek_3 = "deepseek_3"
    deepseek_r1 = "deepseek_r1"
    mistral_small_3 = "mistral_small_3"
    deepseek_r1_distill_qwen_32b = "deepseek_r1_distill_qwen_32b"
    deepseek_r1_distill_llama_70b = "deepseek_r1_distill_llama_70b"
    deepseek_r1_distill_qwen_14b = "deepseek_r1_distill_qwen_14b"
    deepseek_r1_distill_qwen_1p5b = "deepseek_r1_distill_qwen_1p5b"
    deepseek_r1_distill_qwen_7b = "deepseek_r1_distill_qwen_7b"
    deepseek_r1_distill_llama_8b = "deepseek_r1_distill_llama_8b"
    dolphin_2_9_8x22b = "dolphin_2_9_8x22b"
    grok_2 = "grok_2"


class ModelParserID(str, Enum):
    """
    Enumeration of supported model parsers.
    """

    r1_thinking = "r1_thinking"


class KilnModelProvider(BaseModel):
    """
    Configuration for a specific model provider.

    Attributes:
        name: The provider's identifier
        supports_structured_output: Whether the provider supports structured output formats
        supports_data_gen: Whether the provider supports data generation
        untested_model: Whether the model is untested (typically user added). The supports_ fields are not applicable.
        provider_finetune_id: The finetune ID for the provider, if applicable. Some providers like Fireworks load these from an API.
        structured_output_mode: The mode we should use to call the model for structured output, if it was trained with structured output.
        parser: A parser to use for the model, if applicable
        reasoning_capable: Whether the model is designed to output thinking in a structured format (eg <think></think>). If so we don't use COT across 2 calls, and ask for thinking and final response in the same call.
    """

    name: ModelProviderName
    model_id: str | None = None
    supports_structured_output: bool = True
    supports_data_gen: bool = True
    untested_model: bool = False
    provider_finetune_id: str | None = None
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.default
    parser: ModelParserID | None = None
    reasoning_capable: bool = False
    supports_logprobs: bool = False

    # TODO P1: Need a more generalized way to handle custom provider parameters.
    # Making them quite declarative here for now, isolating provider specific logic
    # to this file. Later I should be able to override anything in this file via config.
    r1_openrouter_options: bool = False
    require_openrouter_reasoning: bool = False
    logprobs_openrouter_options: bool = False
    openrouter_skip_required_parameters: bool = False
    thinking_level: Literal["low", "medium", "high"] | None = None
    ollama_model_aliases: List[str] | None = None
    anthropic_extended_thinking: bool = False


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


built_in_models: List[KilnModel] = [
    # GPT 4o Mini
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_4o_mini,
        friendly_name="GPT 4o Mini",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="gpt-4o-mini",
                provider_finetune_id="gpt-4o-mini-2024-07-18",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_logprobs=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/gpt-4o-mini",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_logprobs=True,
                logprobs_openrouter_options=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="gpt-4o-mini",
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
                model_id="gpt-4o",
                provider_finetune_id="gpt-4o-2024-08-06",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_logprobs=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/gpt-4o",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_logprobs=True,
                logprobs_openrouter_options=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="gpt-4o",
            ),
        ],
    ),
    # GPT o3 Mini Low
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o3_mini_low,
        friendly_name="GPT o3 Mini - Low",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o3-mini",
                thinking_level="low",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o3-mini",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="low",
            ),
        ],
    ),
    # GPT o3 Mini Medium
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o3_mini_medium,
        friendly_name="GPT o3 Mini - Medium",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o3-mini",
                thinking_level="medium",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o3-mini",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="medium",
            ),
        ],
    ),
    # GPT o3 Mini High
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o3_mini_high,
        friendly_name="GPT o3 Mini - High",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o3-mini",
                thinking_level="high",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o3-mini",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="high",
            ),
        ],
    ),
    # GPT o1 Low
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o1_low,
        friendly_name="GPT o1 - Low",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o1",
                thinking_level="low",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o1",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="low",
            ),
        ],
    ),
    # GPT o1 Medium
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o1_medium,
        friendly_name="GPT o1 - Medium",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o1",
                thinking_level="medium",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o1",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="medium",
            ),
        ],
    ),
    # GPT o1 High
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o1_high,
        friendly_name="GPT o1 - High",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o1",
                thinking_level="high",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o1",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="high",
            ),
        ],
    ),
    # Claude 3.5 Haiku
    KilnModel(
        family=ModelFamily.claude,
        name=ModelName.claude_3_5_haiku,
        friendly_name="Claude 3.5 Haiku",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.function_calling,
                model_id="anthropic/claude-3-5-haiku",
            ),
            KilnModelProvider(
                name=ModelProviderName.anthropic,
                model_id="claude-3-5-haiku-20241022",
                structured_output_mode=StructuredOutputMode.function_calling,
            ),
            KilnModelProvider(
                name=ModelProviderName.vertex,
                model_id="claude-3-5-haiku",
                structured_output_mode=StructuredOutputMode.function_calling_weak,
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
                structured_output_mode=StructuredOutputMode.function_calling,
                model_id="anthropic/claude-3.5-sonnet",
            ),
            KilnModelProvider(
                name=ModelProviderName.anthropic,
                model_id="claude-3-5-sonnet-20241022",
                structured_output_mode=StructuredOutputMode.function_calling,
            ),
            KilnModelProvider(
                name=ModelProviderName.vertex,
                model_id="claude-3-5-sonnet",
                structured_output_mode=StructuredOutputMode.function_calling_weak,
            ),
        ],
    ),
    # Claude 3.7 Sonnet
    KilnModel(
        family=ModelFamily.claude,
        name=ModelName.claude_3_7_sonnet,
        friendly_name="Claude 3.7 Sonnet",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.function_calling,
                model_id="anthropic/claude-3.7-sonnet",
            ),
            KilnModelProvider(
                name=ModelProviderName.anthropic,
                model_id="claude-3-7-sonnet-20250219",
                structured_output_mode=StructuredOutputMode.function_calling,
            ),
        ],
    ),
    # Claude 3.7 Sonnet Thinking
    KilnModel(
        family=ModelFamily.claude,
        name=ModelName.claude_3_7_sonnet_thinking,
        friendly_name="Claude 3.7 Sonnet Thinking",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="anthropic/claude-3.7-sonnet:thinking",
                reasoning_capable=True,
                # For reasoning models, we need to use json_instructions with OpenRouter
                structured_output_mode=StructuredOutputMode.json_instructions,
                require_openrouter_reasoning=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.anthropic,
                reasoning_capable=True,
                model_id="claude-3-7-sonnet-20250219",
                anthropic_extended_thinking=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
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
                model_id="google/gemini-pro-1.5",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-1.5-pro",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
            ),
            KilnModelProvider(
                name=ModelProviderName.vertex,
                model_id="gemini-1.5-pro",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
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
                model_id="google/gemini-flash-1.5",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-1.5-flash",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
            ),
            KilnModelProvider(
                name=ModelProviderName.vertex,
                model_id="gemini-1.5-flash",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
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
                model_id="google/gemini-flash-1.5-8b",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-1.5-flash-8b",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
            ),
        ],
    ),
    # Gemini 2.0 Flash
    KilnModel(
        family=ModelFamily.gemini,
        name=ModelName.gemini_2_0_flash,
        friendly_name="Gemini 2.0 Flash",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="google/gemini-2.0-flash-001",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-2.0-flash",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
            ),
            KilnModelProvider(
                name=ModelProviderName.vertex,
                model_id="gemini-2.0-flash",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
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
                supports_data_gen=False,
                model_id="nvidia/llama-3.1-nemotron-70b-instruct",
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
                model_id="llama-3.1-8b-instant",
            ),
            KilnModelProvider(
                name=ModelProviderName.amazon_bedrock,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_structured_output=False,
                model_id="meta.llama3-1-8b-instruct-v1:0",
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="llama3.1:8b",
                ollama_model_aliases=["llama3.1"],  # 8b is default
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.function_calling,
                model_id="meta-llama/llama-3.1-8b-instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                # JSON mode not ideal (no schema), but tool calling doesn't work on 8b
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
                model_id="accounts/fireworks/models/llama-v3p1-8b-instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.function_calling_weak,
                provider_finetune_id="meta-llama/Meta-Llama-3.1-8B-Instruct",
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
                name=ModelProviderName.amazon_bedrock,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=False,
                model_id="meta.llama3-1-70b-instruct-v1:0",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_data_gen=False,
                # Need to not pass "strict=True" to the function call to get this to work with logprobs for some reason. Openrouter issue.
                structured_output_mode=StructuredOutputMode.function_calling_weak,
                model_id="meta-llama/llama-3.1-70b-instruct",
                supports_logprobs=True,
                logprobs_openrouter_options=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="llama3.1:70b",
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                # Tool calling forces schema -- fireworks doesn't support json_schema, just json_mode
                structured_output_mode=StructuredOutputMode.function_calling_weak,
                model_id="accounts/fireworks/models/llama-v3p1-70b-instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.function_calling_weak,
                provider_finetune_id="meta-llama/Meta-Llama-3.1-70B-Instruct",
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
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=False,
                model_id="meta.llama3-1-405b-instruct-v1:0",
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="llama3.1:405b",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.function_calling,
                model_id="meta-llama/llama-3.1-405b-instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                # No finetune support. https://docs.fireworks.ai/fine-tuning/fine-tuning-models
                structured_output_mode=StructuredOutputMode.function_calling_weak,
                model_id="accounts/fireworks/models/llama-v3p1-405b-instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.function_calling_weak,
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
                model_id="mistralai/mistral-nemo",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
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
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="mistral.mistral-large-2407-v1:0",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="mistralai/mistral-large",
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="mistral-large",
            ),
        ],
    ),
    # Llama 3.2 1B
    KilnModel(
        family=ModelFamily.llama,
        name=ModelName.llama_3_2_1b,
        friendly_name="Llama 3.2 1B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.groq,
                model_id="llama-3.2-1b-preview",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                model_id="meta-llama/llama-3.2-1b-instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="llama3.2:1b",
            ),
            KilnModelProvider(
                name=ModelProviderName.huggingface,
                model_id="meta-llama/Llama-3.2-1B-Instruct",
                supports_structured_output=False,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                provider_finetune_id="meta-llama/Llama-3.2-1B-Instruct",
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
                name=ModelProviderName.groq,
                model_id="llama-3.2-3b-preview",
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="meta-llama/llama-3.2-3b-instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_data_gen=False,
                model_id="llama3.2",
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="accounts/fireworks/models/llama-v3p2-3b-instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.huggingface,
                model_id="meta-llama/Llama-3.2-3B-Instruct",
                supports_structured_output=False,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Llama-3.2-3B-Instruct-Turbo",
                supports_structured_output=False,
                supports_data_gen=False,
                provider_finetune_id="meta-llama/Llama-3.2-3B-Instruct",
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
                name=ModelProviderName.groq,
                model_id="llama-3.2-11b-vision-preview",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                # Best mode, but fails to often to enable without warning
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="meta-llama/llama-3.2-11b-vision-instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="llama3.2-vision",
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                # No finetune support. https://docs.fireworks.ai/fine-tuning/fine-tuning-models
                model_id="accounts/fireworks/models/llama-v3p2-11b-vision-instruct",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.huggingface,
                model_id="meta-llama/Llama-3.2-11B-Vision-Instruct",
                supports_structured_output=False,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
                supports_structured_output=False,
                supports_data_gen=False,
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
                name=ModelProviderName.groq,
                model_id="llama-3.2-90b-vision-preview",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                model_id="meta-llama/llama-3.2-90b-vision-instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="llama3.2-vision:90b",
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                # No finetune support. https://docs.fireworks.ai/fine-tuning/fine-tuning-models
                model_id="accounts/fireworks/models/llama-v3p2-90b-vision-instruct",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo",
                supports_structured_output=False,
                supports_data_gen=False,
            ),
        ],
    ),
    # Llama 3.3 70B
    KilnModel(
        family=ModelFamily.llama,
        name=ModelName.llama_3_3_70b,
        friendly_name="Llama 3.3 70B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="meta-llama/llama-3.3-70b-instruct",
                structured_output_mode=StructuredOutputMode.json_schema,
                # Openrouter not working with json_schema or tools. JSON_schema sometimes works so force that, but not consistently so still not recommended.
                supports_structured_output=False,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.groq,
                supports_structured_output=True,
                supports_data_gen=True,
                model_id="llama-3.3-70b-versatile",
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="llama3.3",
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                # Tool calling forces schema -- fireworks doesn't support json_schema, just json_mode
                structured_output_mode=StructuredOutputMode.function_calling_weak,
                model_id="accounts/fireworks/models/llama-v3p3-70b-instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.vertex,
                model_id="meta/llama-3.3-70b-instruct-maas",
                # Doesn't work, TODO to debug
                supports_structured_output=False,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Llama-3.3-70B-Instruct-Turbo",
                structured_output_mode=StructuredOutputMode.function_calling_weak,
            ),
        ],
    ),
    # Phi 3.5
    KilnModel(
        family=ModelFamily.phi,
        name=ModelName.phi_3_5,
        friendly_name="Phi 3.5",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="phi3.5",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="microsoft/phi-3.5-mini-128k-instruct",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                # No finetune support. https://docs.fireworks.ai/fine-tuning/fine-tuning-models
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="accounts/fireworks/models/phi-3-vision-128k-instruct",
            ),
        ],
    ),
    # Phi 4
    KilnModel(
        family=ModelFamily.phi,
        name=ModelName.phi_4,
        friendly_name="Phi 4 - 14B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="phi4",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                # JSON mode not consistent enough to enable in UI
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
                model_id="microsoft/phi-4",
            ),
        ],
    ),
    # Phi 4 5.6B
    KilnModel(
        family=ModelFamily.phi,
        name=ModelName.phi_4_5p6b,
        friendly_name="Phi 4 - 5.6B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="microsoft/phi-4-multimodal-instruct",
                supports_structured_output=False,
                supports_data_gen=False,
            ),
        ],
    ),
    # Phi 4 Mini
    KilnModel(
        family=ModelFamily.phi,
        name=ModelName.phi_4_mini,
        friendly_name="Phi 4 Mini - 3.8B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="phi4-mini",
            ),
        ],
    ),
    # Gemma 2 2.6b
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_2_2b,
        friendly_name="Gemma 2 2B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_data_gen=False,
                model_id="gemma2:2b",
            ),
        ],
    ),
    # Gemma 2 9b
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_2_9b,
        friendly_name="Gemma 2 9B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_data_gen=False,
                model_id="gemma2:9b",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                # Best mode, but fails to often to enable without warning
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="google/gemma-2-9b-it",
            ),
            # fireworks AI errors - not allowing system role. Exclude until resolved.
        ],
    ),
    # Gemma 2 27b
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_2_27b,
        friendly_name="Gemma 2 27B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_data_gen=False,
                model_id="gemma2:27b",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
                model_id="google/gemma-2-27b-it",
            ),
        ],
    ),
    # Gemma 3 1B
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_3_1b,
        friendly_name="Gemma 3 1B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="gemma3:1b",
                supports_structured_output=False,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                # TODO: swap to non-free model when available (more reliable)
                model_id="google/gemma-3-1b-it:free",
                supports_structured_output=False,
                supports_data_gen=False,
            ),
        ],
    ),
    # Gemma 3 4B
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_3_4b,
        friendly_name="Gemma 3 4B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="gemma3:4b",
                ollama_model_aliases=["gemma3"],
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                # TODO: swap to non-free model when available (more reliable)
                model_id="google/gemma-3-4b-it:free",
            ),
        ],
    ),
    # Gemma 3 12B
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_3_12b,
        friendly_name="Gemma 3 12B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="gemma3:12b",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                # TODO: swap to non-free model when available (more reliable)
                model_id="google/gemma-3-12b-it:free",
            ),
        ],
    ),
    # Gemma 3 27B
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_3_27b,
        friendly_name="Gemma 3 27B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="gemma3:27b",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                model_id="google/gemma-3-27b-it",
            ),
            KilnModelProvider(
                name=ModelProviderName.huggingface,
                model_id="google/gemma-3-27b-it",
                structured_output_mode=StructuredOutputMode.json_instructions,
            ),
        ],
    ),
    # Mixtral 8x7B
    KilnModel(
        family=ModelFamily.mixtral,
        name=ModelName.mixtral_8x7b,
        friendly_name="Mixtral 8x7B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="mistralai/mixtral-8x7b-instruct",
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="mixtral",
            ),
        ],
    ),
    # QwQ 32B
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwq_32b,
        friendly_name="QwQ 32B (Qwen Reasoning)",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwq-32b",
                reasoning_capable=True,
                require_openrouter_reasoning=True,
                r1_openrouter_options=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/qwq-32b",
                reasoning_capable=True,
                parser=ModelParserID.r1_thinking,
                structured_output_mode=StructuredOutputMode.json_instructions,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwq",
                reasoning_capable=True,
                parser=ModelParserID.r1_thinking,
                structured_output_mode=StructuredOutputMode.json_instructions,
            ),
            KilnModelProvider(
                name=ModelProviderName.groq,
                model_id="qwen-qwq-32b",
                reasoning_capable=True,
                parser=ModelParserID.r1_thinking,
                structured_output_mode=StructuredOutputMode.json_instructions,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="Qwen/QwQ-32B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
            ),
        ],
    ),
    # Qwen 2.5 7B
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_2p5_7b,
        friendly_name="Qwen 2.5 7B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen-2.5-7b-instruct",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen2.5",
            ),
        ],
    ),
    # Qwen 2.5 14B
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_2p5_14b,
        friendly_name="Qwen 2.5 14B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                provider_finetune_id="Qwen/Qwen2.5-14B-Instruct",
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen2.5:14b",
                supports_data_gen=False,
            ),
        ],
    ),
    # Qwen 2.5 72B
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_2p5_72b,
        friendly_name="Qwen 2.5 72B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen-2.5-72b-instruct",
                # Not consistent with structure data. Works sometimes but not often
                supports_structured_output=False,
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen2.5:72b",
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/qwen2p5-72b-instruct",
                # Tool calling forces schema -- fireworks doesn't support json_schema, just json_mode
                structured_output_mode=StructuredOutputMode.function_calling_weak,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                provider_finetune_id="Qwen/Qwen2.5-72B-Instruct",
            ),
        ],
    ),
    # Mistral Small 3
    KilnModel(
        family=ModelFamily.mistral,
        name=ModelName.mistral_small_3,
        friendly_name="Mistral Small 3",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                model_id="mistralai/mistral-small-24b-instruct-2501",
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="mistral-small:24b",
            ),
        ],
    ),
    # DeepSeek 3
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_3,
        friendly_name="DeepSeek V3",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="deepseek/deepseek-chat",
                structured_output_mode=StructuredOutputMode.function_calling,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/deepseek-v3",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_structured_output=True,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="deepseek-ai/DeepSeek-V3",
                structured_output_mode=StructuredOutputMode.json_instructions,
            ),
        ],
    ),
    # DeepSeek R1
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_r1,
        friendly_name="DeepSeek R1",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="deepseek/deepseek-r1",
                parser=ModelParserID.r1_thinking,
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                r1_openrouter_options=True,
                require_openrouter_reasoning=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/deepseek-r1",
                parser=ModelParserID.r1_thinking,
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
            ),
            KilnModelProvider(
                # I want your RAM
                name=ModelProviderName.ollama,
                model_id="deepseek-r1:671b",
                parser=ModelParserID.r1_thinking,
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="deepseek-ai/DeepSeek-R1",
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
            ),
        ],
    ),
    # DeepSeek R1 Distill Qwen 32B
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_r1_distill_qwen_32b,
        friendly_name="DeepSeek R1 Distill Qwen 32B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek/deepseek-r1-distill-qwen-32b",
                r1_openrouter_options=True,
                parser=ModelParserID.r1_thinking,
                require_openrouter_reasoning=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek-r1:32b",
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
            ),
        ],
    ),
    # DeepSeek R1 Distill Llama 70B
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_r1_distill_llama_70b,
        friendly_name="DeepSeek R1 Distill Llama 70B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek/deepseek-r1-distill-llama-70b",
                r1_openrouter_options=True,
                require_openrouter_reasoning=True,
                parser=ModelParserID.r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_data_gen=False,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek-r1:70b",
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
            ),
        ],
    ),
    # DeepSeek R1 Distill Qwen 14B
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_r1_distill_qwen_14b,
        friendly_name="DeepSeek R1 Distill Qwen 14B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_data_gen=False,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek/deepseek-r1-distill-qwen-14b",
                r1_openrouter_options=True,
                require_openrouter_reasoning=True,
                openrouter_skip_required_parameters=True,
                parser=ModelParserID.r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_data_gen=False,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek-r1:14b",
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
            ),
        ],
    ),
    # DeepSeek R1 Distill Llama 8B
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_r1_distill_llama_8b,
        friendly_name="DeepSeek R1 Distill Llama 8B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                supports_data_gen=False,
                reasoning_capable=True,
                # Best mode, but fails to often to enable without warning
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek/deepseek-r1-distill-llama-8b",
                r1_openrouter_options=True,
                require_openrouter_reasoning=True,
                openrouter_skip_required_parameters=True,
                parser=ModelParserID.r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_structured_output=False,
                supports_data_gen=False,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                # Best mode, but fails to often to enable without warning
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek-r1:8b",
            ),
        ],
    ),
    # DeepSeek R1 Distill Qwen 7B
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_r1_distill_qwen_7b,
        friendly_name="DeepSeek R1 Distill Qwen 7B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                # Best mode, but fails to often to enable without warning
                supports_structured_output=False,
                supports_data_gen=False,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek-r1:7b",
            ),
        ],
    ),
    # DeepSeek R1 Distill Qwen 1.5B
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_r1_distill_qwen_1p5b,
        friendly_name="DeepSeek R1 Distill Qwen 1.5B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                supports_data_gen=False,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek/deepseek-r1-distill-qwen-1.5b",
                r1_openrouter_options=True,
                require_openrouter_reasoning=True,
                openrouter_skip_required_parameters=True,
                parser=ModelParserID.r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_structured_output=False,
                supports_data_gen=False,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek-r1:1.5b",
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                supports_structured_output=False,
                supports_data_gen=False,
            ),
        ],
    ),
    # Dolphin 2.9 Mixtral 8x22B
    KilnModel(
        family=ModelFamily.dolphin,
        name=ModelName.dolphin_2_9_8x22b,
        friendly_name="Dolphin 2.9 8x22B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=True,
                model_id="dolphin-mixtral:8x22b",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                model_id="cognitivecomputations/dolphin-mixtral-8x22b",
            ),
        ],
    ),
    # Grok 2
    KilnModel(
        family=ModelFamily.grok,
        name=ModelName.grok_2,
        friendly_name="Grok 2",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="x-ai/grok-2-1212",
                supports_structured_output=True,
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
        ],
    ),
]
