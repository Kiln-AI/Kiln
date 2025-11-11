from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from kiln_ai.datamodel.datamodel_enums import ModelProviderName


# temporary workaround until LiteLLM supports OpenRouter embeddings natively
def transform_slug_for_litellm(provider: ModelProviderName, slug: str) -> str:
    """
    Converts an OpenRouter model slug to an OpenAI compatible slug.

    OpenRouter models are prefixed with openrouter/, but LiteLLM does not yet support embeddings
    via OpenRouter.

    However, the OpenRouter API is OpenAI compatible, so we can use it as a custom OpenAI provider
    by prefixing the model ID with openai/.
    """
    if provider == ModelProviderName.openrouter:
        return slug.replace("openrouter/", "openai/")
    return slug


class KilnEmbeddingModelFamily(str, Enum):
    """
    Enumeration of supported embedding model families.
    """

    # for bespoke proprietary models, the family tends to be the same
    # as provider name, but it does not have to be
    openai = "openai"
    gemini = "gemini"
    gemma = "gemma"
    nomic = "nomic"
    qwen = "qwen"
    baai = "baai"
    modernbert = "modernbert"
    intfloat = "intfloat"
    together = "together"
    thenlper = "thenlper"
    where_is_ai = "where_is_ai"
    mixedbread = "mixedbread"
    netease = "netease"
    mistral = "mistral"


class EmbeddingModelName(str, Enum):
    """
    Enumeration of specific model versions supported by the system.
    """

    # Embedding model names are often generic (e.g., "text-embedding"),
    # so we prefix them with the provider name (e.g., "openai_") to ensure
    # uniqueness across providers now and in the future
    openai_text_embedding_3_small = "openai_text_embedding_3_small"
    openai_text_embedding_3_large = "openai_text_embedding_3_large"
    gemini_text_embedding_004 = "gemini_text_embedding_004"
    gemini_embedding_001 = "gemini_embedding_001"
    embedding_gemma_300m = "embedding_gemma_300m"
    nomic_text_embedding_v1_5 = "nomic_text_embedding_v1_5"
    qwen_3_embedding_0p6b = "qwen_3_embedding_0p6b"
    qwen_3_embedding_4b = "qwen_3_embedding_4b"
    qwen_3_embedding_8b = "qwen_3_embedding_8b"
    baai_bge_small_1_5 = "baai_bge_small_1_5"
    baai_bge_base_1_5 = "baai_bge_base_1_5"
    baai_bge_large_1_5 = "baai_bge_large_1_5"
    m2_bert_retrieval_32k = "m2_bert_retrieval_32k"
    gte_modernbert_base = "gte_modernbert_base"
    multilingual_e5_large_instruct = "multilingual_e5_large_instruct"
    thenlper_gte_large = "thenlper_gte_large"
    thenlper_gte_base = "thenlper_gte_base"
    where_is_ai_uae_large_v1 = "where_is_ai_uae_large_v1"
    mixedbread_ai_mxbai_embed_large_v1 = "mixedbread_ai_mxbai_embed_large_v1"
    netease_youdao_bce_embedding_base_v1 = "netease_youdao_bce_embedding_base_v1"
    openai_text_embedding_ada_002 = "openai_text_embedding_ada_002"
    mistral_embed_text_2312 = "mistral_embed_text_2312"
    mistral_codestral_embed_2505 = "mistral_codestral_embed_2505"


class KilnEmbeddingModelProvider(BaseModel):
    name: ModelProviderName

    model_id: str = Field(
        description="The model ID for the embedding model. This is the ID used to identify the model in the provider's API.",
    )

    max_input_tokens: int | None = Field(
        default=None,
        description="The maximum number of tokens that can be input to the model.",
    )

    n_dimensions: int = Field(
        description="The number of dimensions in the output embedding.",
    )

    supports_custom_dimensions: bool = Field(
        default=False,
        description="Whether the model supports setting a custom output dimension. If true, the user can set the output dimension in the UI.",
    )

    suggested_for_chunk_embedding: bool = Field(
        default=False,
        description="Whether the model is particularly good for chunk embedding.",
    )

    ollama_model_aliases: List[str] | None = None


class KilnEmbeddingModel(BaseModel):
    """
    Configuration for a specific embedding model.
    """

    family: str
    name: str
    friendly_name: str
    providers: List[KilnEmbeddingModelProvider]


built_in_embedding_models: List[KilnEmbeddingModel] = [
    # OpenAI Text Embedding 3 Large
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.openai,
        name=EmbeddingModelName.openai_text_embedding_3_large,
        friendly_name="Text Embedding 3 Large",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openai,
                model_id="text-embedding-3-large",
                n_dimensions=3072,
                max_input_tokens=8192,
                supports_custom_dimensions=True,
                suggested_for_chunk_embedding=True,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/text-embedding-3-large",
                n_dimensions=3072,
                max_input_tokens=8192,
                # litellm rejecting - but model itself supports it
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # OpenAI Text Embedding 3 Small
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.openai,
        name=EmbeddingModelName.openai_text_embedding_3_small,
        friendly_name="Text Embedding 3 Small",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openai,
                model_id="text-embedding-3-small",
                n_dimensions=1536,
                max_input_tokens=8192,
                supports_custom_dimensions=True,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/text-embedding-3-small",
                n_dimensions=1536,
                max_input_tokens=8192,
                # litellm rejecting - but model itself supports it
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # OpenAI Text Embedding ada-002
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.openai,
        name=EmbeddingModelName.openai_text_embedding_ada_002,
        friendly_name="Text Embedding Ada 002",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openai,
                model_id="text-embedding-ada-002",
                n_dimensions=1536,
                max_input_tokens=8192,
                supports_custom_dimensions=False,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openrouter,
                model_id="openai/text-embedding-ada-002",
                n_dimensions=1536,
                max_input_tokens=8192,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Gemini Embedding 001
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.gemini,
        name=EmbeddingModelName.gemini_embedding_001,
        friendly_name="Gemini Embedding 001",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="gemini-embedding-001",
                n_dimensions=3072,
                max_input_tokens=2048,
                supports_custom_dimensions=True,
                suggested_for_chunk_embedding=True,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openrouter,
                model_id="google/gemini-embedding-001",
                n_dimensions=3072,
                max_input_tokens=2048,
                # litellm rejecting - but model itself supports it
                supports_custom_dimensions=False,
                suggested_for_chunk_embedding=True,
            ),
        ],
    ),
    # Gemini Text Embedding 004
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.gemini,
        name=EmbeddingModelName.gemini_text_embedding_004,
        friendly_name="Text Embedding 004",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="text-embedding-004",
                n_dimensions=768,
                max_input_tokens=2048,
            ),
        ],
    ),
    # Embedding Gemma 300m
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.gemma,
        name=EmbeddingModelName.embedding_gemma_300m,
        friendly_name="Embedding Gemma 300m",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.ollama,
                model_id="embeddinggemma:300m",
                n_dimensions=768,
                max_input_tokens=2048,
                # the model itself does support custom dimensions, but not working
                # because litellm rejects the param:
                # https://github.com/BerriAI/litellm/issues/11940
                supports_custom_dimensions=False,
                ollama_model_aliases=["embeddinggemma"],
            ),
        ],
    ),
    # Nomic Embed Text v1.5
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.nomic,
        name=EmbeddingModelName.nomic_text_embedding_v1_5,
        friendly_name="Nomic Embed Text v1.5",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.ollama,
                model_id="nomic-embed-text:v1.5",
                n_dimensions=768,
                max_input_tokens=8192,
                # the model itself does support custom dimensions, but not working
                # because litellm rejects the param:
                # https://github.com/BerriAI/litellm/issues/11940
                supports_custom_dimensions=False,
                ollama_model_aliases=["nomic-embed-text"],
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="nomic-ai/nomic-embed-text-v1.5",
                n_dimensions=768,
                max_input_tokens=8192,
                supports_custom_dimensions=True,
            ),
        ],
    ),
    # Qwen3 Embedding 8B
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.qwen,
        name=EmbeddingModelName.qwen_3_embedding_8b,
        friendly_name="Qwen 3 Embedding 8B",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3-embedding:8b",
                n_dimensions=4096,
                max_input_tokens=32_000,
                # the model itself does support custom dimensions, but not working
                # because litellm rejects the param:
                # https://github.com/BerriAI/litellm/issues/11940
                supports_custom_dimensions=False,
                ollama_model_aliases=[
                    # 8b is default
                    "qwen3-embedding",
                ],
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="accounts/fireworks/models/qwen3-embedding-8b",
                n_dimensions=4096,
                max_input_tokens=32_000,
                # the model itself does support custom dimensions, but not working
                supports_custom_dimensions=False,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/Qwen3-Embedding-8B",
                n_dimensions=4096,
                max_input_tokens=32_000,
                # the model itself does support custom dimensions, but not working
                # because litellm rejects the param:
                # https://github.com/BerriAI/litellm/issues/11940
                supports_custom_dimensions=False,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-embedding-8b",
                n_dimensions=4096,
                max_input_tokens=32_000,
                # litellm rejecting - but model itself supports it
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Qwen3 Embedding 4B
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.qwen,
        name=EmbeddingModelName.qwen_3_embedding_4b,
        friendly_name="Qwen 3 Embedding 4B",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3-embedding:4b",
                n_dimensions=2560,
                max_input_tokens=32_000,
                # the model itself does support custom dimensions, but not working
                # because litellm rejects the param:
                # https://github.com/BerriAI/litellm/issues/11940
                supports_custom_dimensions=False,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/Qwen3-Embedding-4B",
                n_dimensions=2560,
                max_input_tokens=32_000,
                # the model itself does support custom dimensions, but not working
                # because litellm rejects the param:
                # https://github.com/BerriAI/litellm/issues/11940
                supports_custom_dimensions=False,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-embedding-4b",
                n_dimensions=2560,
                max_input_tokens=32_000,
                # litellm rejecting - but model itself supports it
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Qwen3 Embedding 0.6B
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.qwen,
        name=EmbeddingModelName.qwen_3_embedding_0p6b,
        friendly_name="Qwen 3 Embedding 0.6B",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.ollama,
                model_id="qwen3-embedding:0.6b",
                n_dimensions=1024,
                max_input_tokens=32_000,
                # the model itself does support custom dimensions, but not working
                # because litellm rejects the param:
                # https://github.com/BerriAI/litellm/issues/11940
                supports_custom_dimensions=False,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="Qwen/Qwen3-Embedding-0.6B",
                n_dimensions=1024,
                max_input_tokens=32_000,
                # the model itself does support custom dimensions, but not working
                # because litellm rejects the param:
                # https://github.com/BerriAI/litellm/issues/11940
                supports_custom_dimensions=False,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openrouter,
                model_id="qwen/qwen3-embedding-0.6b",
                n_dimensions=1024,
                max_input_tokens=32_000,
                # litellm rejecting - but model itself supports it
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # BAAI-Bge-Large-1.5
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.baai,
        name=EmbeddingModelName.baai_bge_large_1_5,
        friendly_name="BAAI Bge Large 1.5",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.together_ai,
                model_id="BAAI/bge-large-en-v1.5",
                n_dimensions=1024,
                max_input_tokens=512,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # BAAI-Bge-Base-1.5
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.baai,
        name=EmbeddingModelName.baai_bge_base_1_5,
        friendly_name="BAAI Bge Base 1.5",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="BAAI/bge-base-en-v1.5",
                n_dimensions=768,
                max_input_tokens=512,
                supports_custom_dimensions=False,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.together_ai,
                model_id="BAAI/bge-base-en-v1.5",
                n_dimensions=768,
                max_input_tokens=512,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # BAAI-Bge-Small-1.5
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.baai,
        name=EmbeddingModelName.baai_bge_small_1_5,
        friendly_name="BAAI Bge Small 1.5",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="BAAI/bge-small-en-v1.5",
                n_dimensions=384,
                max_input_tokens=512,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # M2-BERT-Retrieval-32k
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.together,
        name=EmbeddingModelName.m2_bert_retrieval_32k,
        friendly_name="M2 BERT Retrieval 32k",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.together_ai,
                model_id="togethercomputer/m2-bert-80M-32k-retrieval",
                n_dimensions=768,
                max_input_tokens=32_768,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Gte Modernbert Base
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.modernbert,
        name=EmbeddingModelName.gte_modernbert_base,
        friendly_name="Gte Modernbert Base",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.together_ai,
                model_id="Alibaba-NLP/gte-modernbert-base",
                n_dimensions=768,
                max_input_tokens=8192,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Multilingual E5 Large Instruct
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.intfloat,
        name=EmbeddingModelName.multilingual_e5_large_instruct,
        friendly_name="Multilingual E5 Large Instruct",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.together_ai,
                model_id="intfloat/multilingual-e5-large-instruct",
                n_dimensions=1024,
                max_input_tokens=512,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Thenlper Gte Large
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.thenlper,
        name=EmbeddingModelName.thenlper_gte_large,
        friendly_name="Thenlper Gte Large",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="thenlper/gte-large",
                n_dimensions=1024,
                max_input_tokens=512,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Thenlper Gte Base
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.thenlper,
        name=EmbeddingModelName.thenlper_gte_base,
        friendly_name="Thenlper Gte Base",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="thenlper/gte-base",
                n_dimensions=768,
                max_input_tokens=512,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Where Is AI UAE Large V1
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.where_is_ai,
        name=EmbeddingModelName.where_is_ai_uae_large_v1,
        friendly_name="Where Is AI UAE Large V1",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="WhereIsAI/UAE-Large-V1",
                n_dimensions=1024,
                max_input_tokens=512,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Mixedbread AI Mxbai Embed Large V1
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.mixedbread,
        name=EmbeddingModelName.mixedbread_ai_mxbai_embed_large_v1,
        friendly_name="Mixedbread AI Mxbai Embed Large V1",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.fireworks_ai,
                model_id="mixedbread-ai/mxbai-embed-large-v1",
                n_dimensions=1024,
                max_input_tokens=512,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Netease Youdao Bce Embedding Base V1
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.netease,
        name=EmbeddingModelName.netease_youdao_bce_embedding_base_v1,
        friendly_name="Netease Youdao Bce Embedding Base V1",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.siliconflow_cn,
                model_id="netease-youdao/bce-embedding-base_v1",
                n_dimensions=768,
                max_input_tokens=512,
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Mistral Embed Text 2312
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.mistral,
        name=EmbeddingModelName.mistral_embed_text_2312,
        friendly_name="Mistral Embed Text 2312",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openrouter,
                model_id="mistralai/mistral-embed-2312",
                n_dimensions=1024,
                max_input_tokens=8192,
                # litellm rejecting - but model itself supports it
                supports_custom_dimensions=False,
            ),
        ],
    ),
    # Mistral Codestral Embed 2505
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.mistral,
        name=EmbeddingModelName.mistral_codestral_embed_2505,
        friendly_name="Mistral Codestral Embed 2505",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openrouter,
                model_id="mistralai/codestral-embed-2505",
                n_dimensions=1536,
                max_input_tokens=8192,
                # litellm rejecting - but model itself supports it
                supports_custom_dimensions=False,
            ),
        ],
    ),
]


def get_model_by_name(name: EmbeddingModelName) -> KilnEmbeddingModel:
    for model in built_in_embedding_models:
        if model.name == name:
            return model
    raise ValueError(f"Embedding model {name} not found in the list of built-in models")


def built_in_embedding_models_from_provider(
    provider_name: ModelProviderName, model_name: str
) -> KilnEmbeddingModelProvider | None:
    for model in built_in_embedding_models:
        if model.name == model_name:
            for p in model.providers:
                if p.name == provider_name:
                    return p
    return None
