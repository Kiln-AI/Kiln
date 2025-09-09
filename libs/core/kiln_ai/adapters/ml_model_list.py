from enum import Enum
from typing import List, Literal

from pydantic import BaseModel

from kiln_ai.datamodel.datamodel_enums import (
    ChatStrategy,
    ModelProviderName,
    StructuredOutputMode,
)

"""
Provides model configuration and management for various LLM providers and models.
This module handles the integration with different AI model providers and their respective models,
including configuration, validation, and instantiation of language models.
"""


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
    kimi = "kimi"
    hunyuan = "hunyuan"
    glm = "glm"
    ernie = "ernie"
    minimax = "minimax"
    pangu = "pangu"


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
    llama_4_maverick = "llama_4_maverick"
    llama_4_scout = "llama_4_scout"
    gpt_5 = "gpt_5"
    gpt_5_chat = "gpt_5_chat"
    gpt_5_mini = "gpt_5_mini"
    gpt_5_nano = "gpt_5_nano"
    gpt_4o_mini = "gpt_4o_mini"
    gpt_4o = "gpt_4o"
    gpt_4_1 = "gpt_4_1"
    gpt_4_1_mini = "gpt_4_1_mini"
    gpt_4_1_nano = "gpt_4_1_nano"
    gpt_o3_low = "gpt_o3_low"
    gpt_o3_medium = "gpt_o3_medium"
    gpt_o3_high = "gpt_o3_high"
    gpt_oss_20b = "gpt_oss_20b"
    gpt_oss_120b = "gpt_oss_120b"
    gpt_o1_low = "gpt_o1_low"
    gpt_o1_medium = "gpt_o1_medium"
    gpt_o1_high = "gpt_o1_high"
    gpt_o4_mini_low = "gpt_o4_mini_low"
    gpt_o4_mini_medium = "gpt_o4_mini_medium"
    gpt_o4_mini_high = "gpt_o4_mini_high"
    gpt_o3_mini_low = "gpt_o3_mini_low"
    gpt_o3_mini_medium = "gpt_o3_mini_medium"
    gpt_o3_mini_high = "gpt_o3_mini_high"
    phi_3_5 = "phi_3_5"
    phi_4 = "phi_4"
    phi_4_5p6b = "phi_4_5p6b"
    phi_4_mini = "phi_4_mini"
    mistral_large = "mistral_large"
    mistral_nemo = "mistral_nemo"
    mistral_small_3 = "mistral_small_3"
    magistral_medium = "magistral_medium"
    magistral_medium_thinking = "magistral_medium_thinking"
    gemma_2_2b = "gemma_2_2b"
    gemma_2_9b = "gemma_2_9b"
    gemma_2_27b = "gemma_2_27b"
    gemma_3_0p27b = "gemma_3_0p27b"
    gemma_3_1b = "gemma_3_1b"
    gemma_3_4b = "gemma_3_4b"
    gemma_3_12b = "gemma_3_12b"
    gemma_3_27b = "gemma_3_27b"
    gemma_3n_2b = "gemma_3n_2b"
    gemma_3n_4b = "gemma_3n_4b"
    claude_3_5_haiku = "claude_3_5_haiku"
    claude_3_5_sonnet = "claude_3_5_sonnet"
    claude_3_7_sonnet = "claude_3_7_sonnet"
    claude_3_7_sonnet_thinking = "claude_3_7_sonnet_thinking"
    claude_sonnet_4 = "claude_sonnet_4"
    claude_opus_4 = "claude_opus_4"
    gemini_1_5_flash = "gemini_1_5_flash"
    gemini_1_5_flash_8b = "gemini_1_5_flash_8b"
    gemini_1_5_pro = "gemini_1_5_pro"
    gemini_2_0_flash = "gemini_2_0_flash"
    gemini_2_0_flash_lite = "gemini_2_0_flash_lite"
    gemini_2_5_pro = "gemini_2_5_pro"
    gemini_2_5_flash = "gemini_2_5_flash"
    gemini_2_5_flash_lite = "gemini_2_5_flash_lite"
    nemotron_70b = "nemotron_70b"
    mixtral_8x7b = "mixtral_8x7b"
    qwen_2p5_7b = "qwen_2p5_7b"
    qwen_2p5_14b = "qwen_2p5_14b"
    qwen_2p5_72b = "qwen_2p5_72b"
    qwq_32b = "qwq_32b"
    deepseek_3_1 = "deepseek_3_1"
    deepseek_3 = "deepseek_3"
    deepseek_r1 = "deepseek_r1"
    deepseek_r1_0528 = "deepseek_r1_0528"
    deepseek_r1_0528_distill_qwen3_8b = "deepseek_r1_0528_distill_qwen3_8b"
    deepseek_r1_distill_qwen_32b = "deepseek_r1_distill_qwen_32b"
    deepseek_r1_distill_llama_70b = "deepseek_r1_distill_llama_70b"
    deepseek_r1_distill_qwen_14b = "deepseek_r1_distill_qwen_14b"
    deepseek_r1_distill_qwen_1p5b = "deepseek_r1_distill_qwen_1p5b"
    deepseek_r1_distill_qwen_7b = "deepseek_r1_distill_qwen_7b"
    deepseek_r1_distill_llama_8b = "deepseek_r1_distill_llama_8b"
    dolphin_2_9_8x22b = "dolphin_2_9_8x22b"
    grok_2 = "grok_2"
    grok_3 = "grok_3"
    grok_3_mini = "grok_3_mini"
    grok_4 = "grok_4"
    qwen_3_0p6b = "qwen_3_0p6b"
    qwen_3_0p6b_no_thinking = "qwen_3_0p6b_no_thinking"
    qwen_3_1p7b = "qwen_3_1p7b"
    qwen_3_1p7b_no_thinking = "qwen_3_1p7b_no_thinking"
    qwen_3_4b = "qwen_3_4b"
    qwen_3_4b_no_thinking = "qwen_3_4b_no_thinking"
    qwen_3_8b = "qwen_3_8b"
    qwen_3_8b_no_thinking = "qwen_3_8b_no_thinking"
    qwen_3_14b = "qwen_3_14b"
    qwen_3_14b_no_thinking = "qwen_3_14b_no_thinking"
    qwen_3_30b_a3b_2507 = "qwen_3_30b_a3b_2507"
    qwen_3_30b_a3b = "qwen_3_30b_a3b"
    qwen_3_30b_a3b_2507_no_thinking = "qwen_3_30b_a3b_2507_no_thinking"
    qwen_3_30b_a3b_no_thinking = "qwen_3_30b_a3b_no_thinking"
    qwen_3_32b = "qwen_3_32b"
    qwen_3_32b_no_thinking = "qwen_3_32b_no_thinking"
    qwen_3_235b_a22b_2507 = "qwen_3_235b_a22b_2507"
    qwen_3_235b_a22b = "qwen_3_235b_a22b"
    qwen_3_235b_a22b_2507_no_thinking = "qwen_3_235b_a22b_2507_no_thinking"
    qwen_3_235b_a22b_no_thinking = "qwen_3_235b_a22b_no_thinking"
    qwen_long_l1_32b = "qwen_long_l1_32b"
    kimi_k2 = "kimi_k2"
    kimi_dev_72b = "kimi_dev_72b"
    glm_4_5 = "glm_4_5"
    glm_4_5_air = "glm_4_5_air"
    glm_4_1v_9b_thinking = "glm_4_1v_9b_thinking"
    glm_z1_32b_0414 = "glm_z1_32b_0414"
    glm_z1_9b_0414 = "glm_z1_9b_0414"
    ernie_4_5_300b_a47b = "ernie_4_5_300b_a47b"
    hunyuan_a13b = "hunyuan_a13b"
    hunyuan_a13b_no_thinking = "hunyuan_a13b_no_thinking"
    minimax_m1_80k = "minimax_m1_80k"
    pangu_pro_moe_72b_a16b = "pangu_pro_moe_72b_a16b"


class ModelParserID(str, Enum):
    """
    Enumeration of supported model parsers.
    """

    r1_thinking = "r1_thinking"
    optional_r1_thinking = "optional_r1_thinking"


class ModelFormatterID(str, Enum):
    """
    Enumeration of supported model formatters.
    """

    qwen3_style_no_think = "qwen3_style_no_think"


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
        tuned_chat_strategy: Used when a model is finetuned with a specific chat strategy, and it's best to use it at call time.
    """

    name: ModelProviderName
    model_id: str | None = None
    supports_structured_output: bool = True
    supports_data_gen: bool = True
    suggested_for_data_gen: bool = False
    untested_model: bool = False
    provider_finetune_id: str | None = None
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.default
    parser: ModelParserID | None = None
    formatter: ModelFormatterID | None = None
    reasoning_capable: bool = False
    supports_logprobs: bool = False
    suggested_for_evals: bool = False
    supports_function_calling: bool = True
    uncensored: bool = False
    suggested_for_uncensored_data_gen: bool = False
    tuned_chat_strategy: ChatStrategy | None = None

    # We need a more generalized way to handle custom provider parameters.
    # Making them quite declarative here for now, isolating provider specific logic
    # to this file. Later I should be able to override anything in this file via config.
    r1_openrouter_options: bool = False
    require_openrouter_reasoning: bool = False
    logprobs_openrouter_options: bool = False
    openrouter_skip_required_parameters: bool = False
    thinking_level: Literal["low", "medium", "high"] | None = None
    ollama_model_aliases: List[str] | None = None
    anthropic_extended_thinking: bool = False
    gemini_reasoning_enabled: bool = False

    # some models on siliconflow allow dynamically disabling thinking
    # currently only supported by Qwen3 and tencent/Hunyuan-A13B-Instruct
    # ref: https://docs.siliconflow.cn/cn/api-reference/chat-completions/chat-completions
    siliconflow_enable_thinking: bool | None = None
    # enable this flag to make reasoning optional for structured output
    # some reasoning models on siliconflow do not return any reasoning for structured output
    # this is not uniform nor documented, so we need to test each model
    reasoning_optional_for_structured_output: bool | None = None


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
    # GPT 5
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_5,
        friendly_name="GPT-5",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="gpt-5",
                structured_output_mode=StructuredOutputMode.json_schema,
                suggested_for_data_gen=True,
                suggested_for_evals=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/gpt-5",
                structured_output_mode=StructuredOutputMode.json_schema,
                suggested_for_data_gen=True,
                suggested_for_evals=True,
            ),
        ],
    ),
    # GPT 5 Mini
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_5_mini,
        friendly_name="GPT-5 Mini",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="gpt-5-mini",
                structured_output_mode=StructuredOutputMode.json_schema,
                suggested_for_evals=True,
                suggested_for_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/gpt-5-mini",
                structured_output_mode=StructuredOutputMode.json_schema,
                suggested_for_evals=True,
                suggested_for_data_gen=True,
            ),
        ],
    ),
    # GPT 5 Nano
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_5_nano,
        friendly_name="GPT-5 Nano",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="gpt-5-nano",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/gpt-5-nano",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
        ],
    ),
    # GPT 5 Chat
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_5_chat,
        friendly_name="GPT-5 Chat",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="gpt-5-chat-latest",
                # Oddly no json_schema support for this model.
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_function_calling=False,
            ),
        ],
    ),
    # GPT 4.1
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_4_1,
        friendly_name="GPT 4.1",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="gpt-4.1",
                provider_finetune_id="gpt-4.1-2025-04-14",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_logprobs=True,
                suggested_for_evals=True,
                suggested_for_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/gpt-4.1",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_logprobs=True,
                suggested_for_evals=True,
                suggested_for_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="gpt-4.1",
                suggested_for_evals=True,
                suggested_for_data_gen=True,
            ),
        ],
    ),
    # GPT 4.1 Mini
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_4_1_mini,
        friendly_name="GPT 4.1 Mini",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="gpt-4.1-mini",
                provider_finetune_id="gpt-4.1-mini-2025-04-14",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_logprobs=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/gpt-4.1-mini",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_logprobs=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="gpt-4.1-mini",
            ),
        ],
    ),
    # GPT 4.1 Nano
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_4_1_nano,
        friendly_name="GPT 4.1 Nano",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="gpt-4.1-nano",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_logprobs=True,
                provider_finetune_id="gpt-4.1-nano-2025-04-14",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/gpt-4.1-nano",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_logprobs=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="gpt-4.1-nano",
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
                suggested_for_data_gen=True,
                suggested_for_evals=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/gpt-4o",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_logprobs=True,
                logprobs_openrouter_options=True,
                suggested_for_data_gen=True,
                suggested_for_evals=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="gpt-4o",
                suggested_for_data_gen=True,
                suggested_for_evals=True,
            ),
        ],
    ),
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
    # GPT o4 Mini Low
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o4_mini_low,
        friendly_name="GPT o4 Mini - Low",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o4-mini",
                thinking_level="low",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o4-mini",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="low",
            ),
        ],
    ),
    # GPT o4 Mini Medium
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o4_mini_medium,
        friendly_name="GPT o4 Mini - Medium",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o4-mini",
                thinking_level="medium",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o4-mini",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="medium",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/o4-mini",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
        ],
    ),
    # GPT o4 Mini High
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o4_mini_high,
        friendly_name="GPT o4 Mini - High",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o4-mini",
                thinking_level="high",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o4-mini",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="high",
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/o4-mini-high",
                structured_output_mode=StructuredOutputMode.json_schema,
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
    # GPT o3 Low
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o3_low,
        friendly_name="GPT o3 - Low",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o3",
                thinking_level="low",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o3",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="low",
            ),
        ],
    ),
    # GPT o3 Medium
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o3_medium,
        friendly_name="GPT o3 - Medium",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o3",
                thinking_level="medium",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o3",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="medium",
            ),
        ],
    ),
    # GPT o3 High
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_o3_high,
        friendly_name="GPT o3 - High",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openai,
                model_id="o3",
                thinking_level="high",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.azure_openai,
                model_id="o3",
                structured_output_mode=StructuredOutputMode.json_schema,
                thinking_level="high",
            ),
        ],
    ),
    # GPT OSS 120B
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_oss_120b,
        friendly_name="GPT OSS 120B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/gpt-oss-120b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                require_openrouter_reasoning=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.groq,
                model_id="openai/gpt-oss-120b",
                structured_output_mode=StructuredOutputMode.json_instructions,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/gpt-oss-120b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="gpt-oss:120b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
            ),
        ],
    ),
    # GPT OSS 20B
    KilnModel(
        family=ModelFamily.gpt,
        name=ModelName.gpt_oss_20b,
        friendly_name="GPT OSS 20B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/gpt-oss-20b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                require_openrouter_reasoning=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.groq,
                model_id="openai/gpt-oss-20b",
                structured_output_mode=StructuredOutputMode.json_instructions,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/gpt-oss-20b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="gpt-oss:20b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
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
    # Claude Sonnet 4
    KilnModel(
        family=ModelFamily.claude,
        name=ModelName.claude_sonnet_4,
        friendly_name="Claude 4 Sonnet",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="anthropic/claude-sonnet-4",
                structured_output_mode=StructuredOutputMode.function_calling,
                suggested_for_data_gen=True,
                suggested_for_evals=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.anthropic,
                model_id="claude-sonnet-4-20250514",
                structured_output_mode=StructuredOutputMode.function_calling,
                suggested_for_data_gen=True,
                suggested_for_evals=True,
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
    # Claude Opus 4
    KilnModel(
        family=ModelFamily.claude,
        name=ModelName.claude_opus_4,
        friendly_name="Claude Opus 4",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="anthropic/claude-opus-4",
                structured_output_mode=StructuredOutputMode.function_calling,
            ),
            KilnModelProvider(
                name=ModelProviderName.anthropic,
                model_id="claude-opus-4-20250514",
                structured_output_mode=StructuredOutputMode.function_calling,
            ),
        ],
    ),
    # Gemini 2.5 Pro
    KilnModel(
        family=ModelFamily.gemini,
        name=ModelName.gemini_2_5_pro,
        friendly_name="Gemini 2.5 Pro",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="google/gemini-2.5-pro",
                structured_output_mode=StructuredOutputMode.json_schema,
                suggested_for_data_gen=True,
                suggested_for_evals=True,
                reasoning_capable=True,
                gemini_reasoning_enabled=True,
                thinking_level="medium",
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-2.5-pro",
                structured_output_mode=StructuredOutputMode.json_schema,
                suggested_for_data_gen=True,
                suggested_for_evals=True,
                reasoning_capable=True,
                gemini_reasoning_enabled=True,
                thinking_level="medium",
            ),
            KilnModelProvider(
                name=ModelProviderName.vertex,
                model_id="gemini-2.5-pro",
                structured_output_mode=StructuredOutputMode.json_schema,
                suggested_for_data_gen=True,
                suggested_for_evals=True,
                reasoning_capable=True,
                gemini_reasoning_enabled=True,
                thinking_level="medium",
            ),
        ],
    ),
    # Gemini 2.5 Flash
    KilnModel(
        family=ModelFamily.gemini,
        name=ModelName.gemini_2_5_flash,
        friendly_name="Gemini 2.5 Flash",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="google/gemini-2.5-flash",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                gemini_reasoning_enabled=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-2.5-flash",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                thinking_level="medium",
            ),
            KilnModelProvider(
                name=ModelProviderName.vertex,
                model_id="gemini-2.5-flash",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                thinking_level="medium",
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
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-2.0-flash",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.vertex,
                model_id="gemini-2.0-flash",
                structured_output_mode=StructuredOutputMode.json_schema,
                provider_finetune_id="gemini-2.0-flash-001",
            ),
        ],
    ),
    # Gemini 2.0 Flash Lite
    KilnModel(
        family=ModelFamily.gemini,
        name=ModelName.gemini_2_0_flash_lite,
        friendly_name="Gemini 2.0 Flash Lite",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="google/gemini-2.0-flash-lite-001",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-2.0-flash-lite",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.vertex,
                model_id="gemini-2.0-flash-lite",
                structured_output_mode=StructuredOutputMode.json_schema,
                provider_finetune_id="gemini-2.0-flash-lite-001",
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
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-1.5-pro",
                structured_output_mode=StructuredOutputMode.json_schema,
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
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-1.5-flash",
                structured_output_mode=StructuredOutputMode.json_schema,
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
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-1.5-flash-8b",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=False,
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
                supports_function_calling=False,
            ),
        ],
    ),
    # Llama 4 Maverick Basic
    KilnModel(
        family=ModelFamily.llama,
        name=ModelName.llama_4_maverick,
        friendly_name="Llama 4 Maverick",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="meta-llama/llama-4-maverick",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/llama4-maverick-instruct-basic",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.cerebras,
                model_id="llama-4-maverick-17b-128e-instruct",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
        ],
    ),
    # Llama 4 Scout Basic
    KilnModel(
        family=ModelFamily.llama,
        name=ModelName.llama_4_scout,
        friendly_name="Llama 4 Scout",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="meta-llama/llama-4-scout",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/llama4-scout-instruct-basic",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Llama-4-Scout-17B-16E-Instruct",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.cerebras,
                model_id="llama-4-scout-17b-16e-instruct",
                structured_output_mode=StructuredOutputMode.json_schema,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.amazon_bedrock,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_structured_output=False,
                model_id="meta.llama3-1-8b-instruct-v1:0",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="llama3.1:8b",
                ollama_model_aliases=["llama3.1"],  # 8b is default
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.function_calling,
                model_id="meta-llama/llama-3.1-8b-instruct",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                # JSON mode not ideal (no schema), but tool calling doesn't work on 8b
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
                model_id="accounts/fireworks/models/llama-v3p1-8b-instruct",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.function_calling_weak,
                provider_finetune_id="meta-llama/Meta-Llama-3.1-8B-Instruct-Reference",
                # Constrained decode? They make function calling work when no one else does!
            ),
            KilnModelProvider(
                name=ModelProviderName.cerebras,
                model_id="llama3.1-8b",
                structured_output_mode=StructuredOutputMode.function_calling,
                supports_data_gen=False,
                suggested_for_evals=False,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="ai/llama3.1:8B-Q4_K_M",
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="meta-llama/llama-3.1-70b-instruct",
                supports_logprobs=True,
                logprobs_openrouter_options=True,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="llama3.1:70b",
                supports_function_calling=False,
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
                provider_finetune_id="meta-llama/Meta-Llama-3.1-70B-Instruct-Reference",
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
                supports_function_calling=False,  # Not reliable
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
    # Magistral Medium (Thinking)
    KilnModel(
        family=ModelFamily.mistral,
        name=ModelName.magistral_medium_thinking,
        friendly_name="Magistral Medium (Thinking)",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="mistralai/magistral-medium-2506:thinking",
                structured_output_mode=StructuredOutputMode.json_schema,
                # Thinking tokens are hidden by Mistral so not "reasoning" from Kiln API POV
            ),
        ],
    ),
    # Magistral Medium (No Thinking)
    KilnModel(
        family=ModelFamily.mistral,
        name=ModelName.magistral_medium,
        friendly_name="Magistral Medium (No Thinking)",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="mistralai/magistral-medium-2506",
                structured_output_mode=StructuredOutputMode.json_schema,
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
                supports_function_calling=False,  # Not reliable
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/mistral-nemo:12B-Q4_K_M",
                structured_output_mode=StructuredOutputMode.json_schema,
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
                uncensored=True,
                suggested_for_uncensored_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="mistralai/mistral-large",
                uncensored=True,
                suggested_for_uncensored_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="mistral-large",
                uncensored=True,
                suggested_for_uncensored_data_gen=True,
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
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                model_id="meta-llama/llama-3.2-1b-instruct",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="llama3.2:1b",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="ai/llama3.2:1B-F16",
                supports_function_calling=False,
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
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="meta-llama/llama-3.2-3b-instruct",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_data_gen=False,
                model_id="llama3.2",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Llama-3.2-3B-Instruct-Turbo",
                supports_structured_output=False,
                supports_data_gen=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/llama3.2:3B-Q4_K_M",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=False,
                supports_function_calling=False,
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
                # Best mode, but fails to often to enable without warning
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="meta-llama/llama-3.2-11b-vision-instruct",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="llama3.2-vision",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
                supports_structured_output=False,
                supports_data_gen=False,
                supports_function_calling=False,  # weird 3b works and 11b doesn't but... vision?
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
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                model_id="meta-llama/llama-3.2-90b-vision-instruct",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="llama3.2-vision:90b",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo",
                supports_structured_output=False,
                supports_data_gen=False,
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.groq,
                supports_structured_output=True,
                supports_data_gen=True,
                model_id="llama-3.3-70b-versatile",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="llama3.3",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                # Tool calling forces schema -- fireworks doesn't support json_schema, just json_mode
                structured_output_mode=StructuredOutputMode.function_calling_weak,
                model_id="accounts/fireworks/models/llama-v3p3-70b-instruct",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.vertex,
                model_id="meta/llama-3.3-70b-instruct-maas",
                # Doesn't work yet; needs debugging
                supports_structured_output=False,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="meta-llama/Llama-3.3-70B-Instruct-Turbo",
                structured_output_mode=StructuredOutputMode.function_calling_weak,
                # Tools work. Probably constrained decode? Nice
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="ai/llama3.3:70B-Q4_K_M",
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="microsoft/phi-3.5-mini-128k-instruct",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                # JSON mode not consistent enough to enable in UI
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
                model_id="microsoft/phi-4",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                structured_output_mode=StructuredOutputMode.json_schema,
                model_id="ai/phi4:14B-Q4_K_M",
                supports_function_calling=False,
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
                supports_function_calling=False,
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
                supports_function_calling=False,
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
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                # Best mode, but fails to often to enable without warning
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="google/gemma-2-9b-it",
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
                model_id="google/gemma-2-27b-it",
                supports_function_calling=False,
            ),
        ],
    ),
    # Gemma 3 270M
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_3_0p27b,
        friendly_name="Gemma 3 270M",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/gemma3:270M-F16",
                supports_structured_output=False,
                supports_data_gen=False,
                supports_function_calling=False,
            )
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/gemma3:1B-F16",
                supports_structured_output=False,
                supports_data_gen=False,
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                model_id="google/gemma-3-4b-it",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/gemma3:4B-Q4_K_M",
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                model_id="google/gemma-3-12b-it",
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                model_id="google/gemma-3-27b-it",
                supports_function_calling=False,
            ),
        ],
    ),
    # Gemma 3n 2B
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_3n_2b,
        friendly_name="Gemma 3n 2B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="gemma3n:e2b",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemma-3n-e2b-it",
                supports_structured_output=False,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
        ],
    ),
    # Gemma 3n 4B
    KilnModel(
        family=ModelFamily.gemma,
        name=ModelName.gemma_3n_4b,
        friendly_name="Gemma 3n 4B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="google/gemma-3n-e4b-it",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="gemma3n:e4b",
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemma-3n-e4b-it",
                structured_output_mode=StructuredOutputMode.json_instructions,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/gemma3n:4B-Q4_K_M",
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="mixtral",
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwq",
                reasoning_capable=True,
                parser=ModelParserID.r1_thinking,
                structured_output_mode=StructuredOutputMode.json_instructions,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="Qwen/QwQ-32B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/QwQ-32B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/qwq:32B-Q4_K_M",
                reasoning_capable=True,
                parser=ModelParserID.r1_thinking,
                structured_output_mode=StructuredOutputMode.json_instructions,
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen2.5",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/qwen2.5:7B-Q4_K_M",
                supports_function_calling=False,
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
                supports_function_calling=False,
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
                uncensored=True,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="mistral-small:24b",
                uncensored=True,
                supports_function_calling=False,
            ),
        ],
    ),
    # DeepSeek R1 0528
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_r1_0528,
        friendly_name="DeepSeek R1 0528",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="deepseek/deepseek-r1-0528",
                parser=ModelParserID.r1_thinking,
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                r1_openrouter_options=True,
                require_openrouter_reasoning=True,
                supports_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/deepseek-r1-0528",
                parser=ModelParserID.r1_thinking,
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="deepseek-ai/DeepSeek-R1",  # Note: Together remapped the R1 endpoint to this 0528 model
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                supports_data_gen=True,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Pro/deepseek-ai/DeepSeek-R1",
                parser=ModelParserID.optional_r1_thinking,
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                supports_data_gen=True,
                supports_function_calling=False,
            ),
        ],
    ),
    # DeepSeek R1 0528 Distill Qwen 3 8B
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_r1_0528_distill_qwen3_8b,
        friendly_name="DeepSeek R1 0528 Distill Qwen 3 8B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="deepseek/deepseek-r1-0528-qwen3-8b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                r1_openrouter_options=True,
                require_openrouter_reasoning=True,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                reasoning_optional_for_structured_output=True,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
        ],
    ),
    # DeepSeek 3.1
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_3_1,
        friendly_name="DeepSeek 3.1",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="deepseek/deepseek-chat-v3.1",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/deepseek-v3p1",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                supports_data_gen=True,
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
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Pro/deepseek-ai/DeepSeek-V3",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
        ],
    ),
    # DeepSeek R1
    KilnModel(
        family=ModelFamily.deepseek,
        name=ModelName.deepseek_r1,
        friendly_name="DeepSeek R1 (Original)",
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                # I want your RAM
                name=ModelProviderName.ollama,
                model_id="deepseek-r1:671b",
                parser=ModelParserID.r1_thinking,
                structured_output_mode=StructuredOutputMode.json_instructions,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek-r1:32b",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                supports_function_calling=False,
                reasoning_optional_for_structured_output=True,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_data_gen=False,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek-r1:70b",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                supports_data_gen=False,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="ai/deepseek-r1-distill-llama:70B-Q4_K_M",
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_data_gen=False,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek-r1:14b",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                reasoning_optional_for_structured_output=True,
                supports_data_gen=False,
                supports_function_calling=False,
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
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                supports_structured_output=False,
                supports_data_gen=False,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                # Best mode, but fails to often to enable without warning
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="ai/deepseek-r1-distill-llama:8B-Q4_K_M",
                supports_function_calling=False,
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
                name=ModelProviderName.openrouter,
                # Best mode, but fails to often to enable without warning
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="deepseek/deepseek-r1-distill-qwen-7b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                r1_openrouter_options=True,
                require_openrouter_reasoning=True,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                # Best mode, but fails to often to enable without warning
                supports_structured_output=False,
                supports_data_gen=False,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek-r1:7b",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                # Best mode, but fails to often to enable without warning
                supports_structured_output=False,
                supports_data_gen=False,
                model_id="Pro/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                reasoning_optional_for_structured_output=True,
                supports_function_calling=False,
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
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                supports_structured_output=False,
                supports_data_gen=False,
                parser=ModelParserID.r1_thinking,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                model_id="deepseek-r1:1.5b",
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                supports_structured_output=False,
                supports_data_gen=False,
                supports_function_calling=False,
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
                uncensored=True,
                suggested_for_uncensored_data_gen=True,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                model_id="cognitivecomputations/dolphin-mixtral-8x22b",
                uncensored=True,
                suggested_for_uncensored_data_gen=True,
                supports_function_calling=False,
            ),
        ],
    ),
    # Grok 4
    KilnModel(
        family=ModelFamily.grok,
        name=ModelName.grok_4,
        friendly_name="Grok 4",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="x-ai/grok-4",
                supports_structured_output=True,
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.json_schema,
                suggested_for_data_gen=True,
                uncensored=True,
                suggested_for_uncensored_data_gen=True,
            ),
        ],
    ),
    # Grok 3
    KilnModel(
        family=ModelFamily.grok,
        name=ModelName.grok_3,
        friendly_name="Grok 3",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="x-ai/grok-3",
                supports_structured_output=True,
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.json_schema,
                suggested_for_data_gen=True,
                uncensored=True,
            ),
        ],
    ),
    # Grok 3 Mini
    KilnModel(
        family=ModelFamily.grok,
        name=ModelName.grok_3_mini,
        friendly_name="Grok 3 Mini",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="x-ai/grok-3-mini",
                supports_structured_output=True,
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.json_schema,
                uncensored=True,
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
    # Qwen 3 0.6B
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_0p6b,
        friendly_name="Qwen 3 0.6B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-0.6b-04-28:free",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                require_openrouter_reasoning=True,
                r1_openrouter_options=True,
                parser=ModelParserID.r1_thinking,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:0.6b",
                supports_data_gen=False,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/qwen3:0.6B-F16",
                supports_data_gen=False,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
        ],
    ),
    # Qwen 3 0.6B Non-Thinking -- not respecting /no_think tag, skipping
    # Qwen 3 1.7B
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_1p7b,
        friendly_name="Qwen 3 1.7B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-1.7b:free",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                require_openrouter_reasoning=True,
                r1_openrouter_options=True,
                parser=ModelParserID.r1_thinking,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:1.7b",
                supports_data_gen=False,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
        ],
    ),
    # Qwen 3 1.7B Non-Thinking
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_1p7b_no_thinking,
        friendly_name="Qwen 3 1.7B Non-Thinking",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-1.7b:free",
                structured_output_mode=StructuredOutputMode.json_instructions,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=False,
                parser=ModelParserID.optional_r1_thinking,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:1.7b",
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=False,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
        ],
    ),
    # Qwen 3 4B
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_4b,
        friendly_name="Qwen 3 4B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-4b:free",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                require_openrouter_reasoning=True,
                r1_openrouter_options=True,
                parser=ModelParserID.r1_thinking,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:4b",
                supports_data_gen=False,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
        ],
    ),
    # Qwen 3 4B Non-Thinking
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_4b_no_thinking,
        friendly_name="Qwen 3 4B Non-Thinking",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-4b:free",
                structured_output_mode=StructuredOutputMode.json_instructions,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=False,
                parser=ModelParserID.optional_r1_thinking,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:4b",
                structured_output_mode=StructuredOutputMode.json_schema,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
        ],
    ),
    # Qwen 3 8B
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_8b,
        friendly_name="Qwen 3 8B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-8b",
                supports_structured_output=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                require_openrouter_reasoning=True,
                r1_openrouter_options=True,
                parser=ModelParserID.r1_thinking,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:8b",
                supports_data_gen=False,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/Qwen3-8B",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                siliconflow_enable_thinking=True,
                reasoning_optional_for_structured_output=True,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/qwen3:8B-Q4_K_M",
                supports_data_gen=False,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
        ],
    ),
    # Qwen 3 8B Non-Thinking
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_8b_no_thinking,
        friendly_name="Qwen 3 8B Non-Thinking",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-8b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=False,
                parser=ModelParserID.optional_r1_thinking,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:8b",
                structured_output_mode=StructuredOutputMode.json_schema,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/Qwen3-8B",
                structured_output_mode=StructuredOutputMode.json_schema,
                siliconflow_enable_thinking=False,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
        ],
    ),
    # Qwen 3 14B
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_14b,
        friendly_name="Qwen 3 14B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-14b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                require_openrouter_reasoning=True,
                r1_openrouter_options=True,
                parser=ModelParserID.r1_thinking,
                supports_data_gen=True,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:14b",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/Qwen3-14B",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=True,
                reasoning_capable=True,
                siliconflow_enable_thinking=True,
                reasoning_optional_for_structured_output=True,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/qwen3:14B-Q6_K",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_function_calling=False,
            ),
        ],
    ),
    # Qwen 3 14B Non-Thinking
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_14b_no_thinking,
        friendly_name="Qwen 3 14B Non-Thinking",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-14b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=True,
                parser=ModelParserID.optional_r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:14b",
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/Qwen3-14B",
                formatter=ModelFormatterID.qwen3_style_no_think,
                structured_output_mode=StructuredOutputMode.json_schema,
                siliconflow_enable_thinking=False,
                supports_data_gen=True,
            ),
        ],
    ),
    # Qwen 3 30B (3B Active) 2507 Version
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_30b_a3b_2507,
        friendly_name="Qwen 3 30B (3B Active) 2507",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:30b-a3b-thinking-2507-q4_K_M",
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.docker_model_runner,
                model_id="ai/qwen3:30B-A3B-Q4_K_M",
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
        ],
    ),
    # Qwen 3 30B (3B Active)
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_30b_a3b,
        friendly_name="Qwen 3 30B (3B Active)",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-30b-a3b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                require_openrouter_reasoning=True,
                r1_openrouter_options=True,
                parser=ModelParserID.r1_thinking,
                supports_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:30b-a3b",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/qwen3-30b-a3b",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/Qwen3-30B-A3B",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                reasoning_optional_for_structured_output=True,
                supports_data_gen=True,
            ),
        ],
    ),
    # Qwen 3 30B (3B Active) 2507 Version Non-Thinking
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_30b_a3b_2507_no_thinking,
        friendly_name="Qwen 3 30B (3B Active) 2507 Non-Thinking",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-30b-a3b-instruct-2507",
                structured_output_mode=StructuredOutputMode.json_instructions,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:30b-a3b-instruct-2507-q8_0",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=True,
            ),
        ],
    ),
    # Qwen 3 30B (3B Active) Non-Thinking
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_30b_a3b_no_thinking,
        friendly_name="Qwen 3 30B (3B Active) Non-Thinking",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-30b-a3b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=True,
                parser=ModelParserID.optional_r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:30b-a3b",
                structured_output_mode=StructuredOutputMode.json_schema,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/qwen3-30b-a3b",
                supports_data_gen=True,
                formatter=ModelFormatterID.qwen3_style_no_think,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.optional_r1_thinking,
            ),
        ],
    ),
    # Qwen 3 32B
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_32b,
        friendly_name="Qwen 3 32B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.groq,
                model_id="Qwen/Qwen3-32B",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                # This model doesn't return reasoning content after a tool call so we need to allow optional reasoning.
                parser=ModelParserID.optional_r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-32b",
                reasoning_capable=True,
                require_openrouter_reasoning=True,
                r1_openrouter_options=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                supports_data_gen=True,
                # Not reliable, even for simple functions
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:32b",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/Qwen3-32B",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                reasoning_optional_for_structured_output=True,
                supports_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.cerebras,
                model_id="qwen-3-32b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                supports_data_gen=True,
                reasoning_capable=True,
                # This model doesn't return reasoning content after a tool call so we need to allow optional reasoning.
                parser=ModelParserID.optional_r1_thinking,
            ),
        ],
    ),
    # Qwen 3 32B No Thinking
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_32b_no_thinking,
        friendly_name="Qwen 3 32B Non-Thinking",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-32b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=True,
                parser=ModelParserID.optional_r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:32b",
                structured_output_mode=StructuredOutputMode.json_schema,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.cerebras,
                model_id="qwen-3-32b",
                structured_output_mode=StructuredOutputMode.json_schema,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=True,
                parser=ModelParserID.optional_r1_thinking,
            ),
        ],
    ),
    # Qwen 3 235B (22B Active) 2507 Version
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_235b_a22b_2507,
        friendly_name="Qwen 3 235B (22B Active) 2507",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-235b-a22b-thinking-2507",
                reasoning_capable=True,
                require_openrouter_reasoning=True,
                supports_data_gen=True,
                suggested_for_data_gen=True,
                r1_openrouter_options=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:235b-a22b-thinking-2507-q4_K_M",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/qwen3-235b-a22b-thinking-2507",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="Qwen/Qwen3-235B-A22B-Thinking-2507",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                supports_function_calling=False,
            ),
        ],
    ),
    # Qwen 3 235B (22B Active)
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_235b_a22b,
        friendly_name="Qwen 3 235B (22B Active)",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-235b-a22b",
                reasoning_capable=True,
                require_openrouter_reasoning=True,
                supports_data_gen=True,
                r1_openrouter_options=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:235b-a22b",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/qwen3-235b-a22b",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="Qwen/Qwen3-235B-A22B-fp8-tput",
                supports_data_gen=True,
                reasoning_capable=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.r1_thinking,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/Qwen3-235B-A22B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                siliconflow_enable_thinking=True,
                supports_data_gen=True,
                suggested_for_data_gen=True,
            ),
        ],
    ),
    # Qwen 3 235B (22B Active) 2507 Version Non-Thinking
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_235b_a22b_2507_no_thinking,
        friendly_name="Qwen 3 235B (22B Active) 2507 Non-Thinking",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-235b-a22b-2507",
                structured_output_mode=StructuredOutputMode.json_instructions,
                supports_data_gen=True,
                reasoning_capable=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:235b-a22b-instruct-2507-q4_K_M",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=True,
                reasoning_capable=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/qwen3-235b-a22b-instruct-2507",
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="Qwen/Qwen3-235B-A22B-Instruct-2507-tput",
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.json_instructions,
                supports_function_calling=False,
            ),
        ],
    ),
    # Qwen 3 235B (22B Active) Non-Thinking
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_3_235b_a22b_no_thinking,
        friendly_name="Qwen 3 235B (22B Active) Non-Thinking",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-235b-a22b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=True,
                reasoning_capable=False,
                parser=ModelParserID.optional_r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3:235b-a22b",
                structured_output_mode=StructuredOutputMode.json_schema,
                formatter=ModelFormatterID.qwen3_style_no_think,
                supports_data_gen=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/qwen3-235b-a22b",
                supports_data_gen=True,
                formatter=ModelFormatterID.qwen3_style_no_think,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.optional_r1_thinking,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="Qwen/Qwen3-235B-A22B-fp8-tput",
                supports_data_gen=True,
                formatter=ModelFormatterID.qwen3_style_no_think,
                structured_output_mode=StructuredOutputMode.json_instructions,
                parser=ModelParserID.optional_r1_thinking,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/Qwen3-235B-A22B",
                structured_output_mode=StructuredOutputMode.json_instructions,
                siliconflow_enable_thinking=False,
                supports_data_gen=True,
            ),
        ],
    ),
    # Qwen Long L1 32B
    KilnModel(
        family=ModelFamily.qwen,
        name=ModelName.qwen_long_l1_32b,
        friendly_name="QwenLong L1 32B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Tongyi-Zhiwen/QwenLong-L1-32B",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                reasoning_optional_for_structured_output=True,
                supports_function_calling=False,
            ),
        ],
    ),
    # GLM 4.5
    KilnModel(
        family=ModelFamily.glm,
        name=ModelName.glm_4_5,
        friendly_name="GLM 4.5",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="z-ai/glm-4.5",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/glm-4p5",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
            ),
        ],
    ),
    # GLM 4.5 AIR
    KilnModel(
        family=ModelFamily.glm,
        name=ModelName.glm_4_5_air,
        friendly_name="GLM 4.5 AIR",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="z-ai/glm-4.5-air",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/glm-4p5-air",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="zai-org/GLM-4.5-Air-FP8",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                parser=ModelParserID.r1_thinking,
            ),
        ],
    ),
    # Kimi K2 Instruct
    KilnModel(
        family=ModelFamily.kimi,
        name=ModelName.kimi_k2,
        friendly_name="Kimi K2",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/kimi-k2-instruct",
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                # Ignoring json mode for now, so not suggested for evals
            ),
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="moonshotai/kimi-k2",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=True,
                suggested_for_evals=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.together_ai,
                model_id="moonshotai/Kimi-K2-Instruct",
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.json_instruction_and_object,
                suggested_for_evals=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.groq,
                model_id="moonshotai/kimi-k2-instruct",
                supports_data_gen=True,
                structured_output_mode=StructuredOutputMode.function_calling,
                suggested_for_evals=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Pro/moonshotai/Kimi-K2-Instruct",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=True,
                suggested_for_evals=True,
            ),
        ],
    ),
    KilnModel(
        family=ModelFamily.kimi,
        name=ModelName.kimi_dev_72b,
        friendly_name="Kimi Dev 72B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="moonshotai/Kimi-Dev-72B",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                reasoning_optional_for_structured_output=True,
                supports_function_calling=False,
            ),
        ],
    ),
    # GLM 4.1V 9B
    KilnModel(
        family=ModelFamily.glm,
        name=ModelName.glm_4_1v_9b_thinking,
        friendly_name="GLM-4.1V 9B Thinking",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Pro/THUDM/GLM-4.1V-9B-Thinking",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
        ],
    ),
    # GLM Z1 32B 0414
    KilnModel(
        family=ModelFamily.glm,
        name=ModelName.glm_z1_32b_0414,
        friendly_name="GLM-Z1 32B 0414",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="THUDM/GLM-Z1-32B-0414",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                reasoning_optional_for_structured_output=True,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
        ],
    ),
    # GLM Z1 9B 0414
    KilnModel(
        family=ModelFamily.glm,
        name=ModelName.glm_z1_9b_0414,
        friendly_name="GLM-Z1 9B 0414",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="THUDM/GLM-Z1-9B-0414",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                reasoning_optional_for_structured_output=True,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
        ],
    ),
    # Ernie 4.5 300B A47B
    KilnModel(
        family=ModelFamily.ernie,
        name=ModelName.ernie_4_5_300b_a47b,
        friendly_name="Ernie 4.5 300B A47B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="baidu/ernie-4.5-300b-a47b",
                structured_output_mode=StructuredOutputMode.json_instructions,
                supports_data_gen=True,
                r1_openrouter_options=True,
                supports_function_calling=False,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="baidu/ERNIE-4.5-300B-A47B",
                structured_output_mode=StructuredOutputMode.json_schema,
                supports_data_gen=True,
                supports_function_calling=False,
            ),
        ],
    ),
    # Hunyuan A13B Instruct
    KilnModel(
        family=ModelFamily.hunyuan,
        name=ModelName.hunyuan_a13b,
        friendly_name="Hunyuan A13B",
        providers=[
            # Openrouter provider for this model exists but currently wrongly parses the answer
            # it returns the reasoning at the right place, but wraps the answer (even JSON response)
            # between <answer> and </answer> tags
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="tencent/Hunyuan-A13B-Instruct",
                structured_output_mode=StructuredOutputMode.json_schema,
                reasoning_capable=True,
                siliconflow_enable_thinking=True,
                reasoning_optional_for_structured_output=True,
                supports_data_gen=False,
                supports_function_calling=False,
            ),
        ],
    ),
    # Minimax M1 80K
    KilnModel(
        family=ModelFamily.minimax,
        name=ModelName.minimax_m1_80k,
        friendly_name="Minimax M1",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.openrouter,
                model_id="minimax/minimax-m1",
                structured_output_mode=StructuredOutputMode.json_instructions,
                supports_data_gen=True,
                r1_openrouter_options=True,
                require_openrouter_reasoning=True,
            ),
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="MiniMaxAI/MiniMax-M1-80k",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                supports_data_gen=True,
                supports_function_calling=False,
            ),
        ],
    ),
    # Pangu Pro MOE
    KilnModel(
        family=ModelFamily.pangu,
        name=ModelName.pangu_pro_moe_72b_a16b,
        friendly_name="Pangu Pro MOE 72B A16B",
        providers=[
            KilnModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="ascend-tribe/pangu-pro-moe",
                structured_output_mode=StructuredOutputMode.json_instructions,
                reasoning_capable=True,
                supports_data_gen=True,
                supports_function_calling=False,
            ),
        ],
    ),
]


def get_model_by_name(name: ModelName) -> KilnModel:
    for model in built_in_models:
        if model.name == name:
            return model
    raise ValueError(f"Model {name} not found in the list of built-in models")


def default_structured_output_mode_for_model_provider(
    model_name: str,
    provider: ModelProviderName,
    default: StructuredOutputMode = StructuredOutputMode.default,
    disallowed_modes: List[StructuredOutputMode] = [],
) -> StructuredOutputMode:
    """
    We don't expose setting this manually in the UI, so pull a recommended mode from ml_model_list
    """
    try:
        # Convert string to ModelName enum
        model_name_enum = ModelName(model_name)
        model = get_model_by_name(model_name_enum)
    except (ValueError, KeyError):
        # If model not found, return default
        return default

    # Find the provider within the model's providers
    for model_provider in model.providers:
        if model_provider.name == provider:
            mode = model_provider.structured_output_mode
            if mode not in disallowed_modes:
                return mode

    # If provider not found, return default
    return default
