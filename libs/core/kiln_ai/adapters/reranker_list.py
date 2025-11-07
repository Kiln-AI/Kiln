from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from kiln_ai.datamodel.datamodel_enums import ModelProviderName


class KilnRerankerModelFamily(str, Enum):
    """
    Enumeration of supported reranker model families.
    """

    llama_rank = "llama_rank"
    vertex_reranker = "vertex_reranker"
    cohere_rerank = "cohere_rerank"
    amazon_rerank = "amazon_rerank"


class RerankerModelName(str, Enum):
    """
    Enumeration of specific model versions supported by the system.
    """

    llama_rank = "llama_rank"
    semantic_ranker_default_004 = "semantic_ranker_default_004"
    semantic_ranker_fast_004 = "semantic_ranker_fast_004"
    cohere_rerank_v3_5 = "cohere_rerank_v3_5"
    amazon_rerank_1_0 = "amazon_rerank_1_0"


class KilnRerankerModelProvider(BaseModel):
    name: ModelProviderName

    model_id: str = Field(
        description="The model ID for the reranker model. This is the ID used to identify the model in the provider's API.",
        min_length=1,
    )


class KilnRerankerModel(BaseModel):
    """
    Configuration for a specific reranker model.
    """

    family: str
    name: str
    friendly_name: str
    providers: List[KilnRerankerModelProvider]


built_in_rerankers: List[KilnRerankerModel] = [
    # LlamaRank
    KilnRerankerModel(
        family=KilnRerankerModelFamily.llama_rank,
        name=RerankerModelName.llama_rank,
        friendly_name="LlamaRank",
        providers=[
            KilnRerankerModelProvider(
                name=ModelProviderName.together_ai,
                model_id="Salesforce/Llama-Rank-V1",
            ),
        ],
    ),
    # semantic-ranker-default-004 (Vertex AI)
    KilnRerankerModel(
        family=KilnRerankerModelFamily.vertex_reranker,
        name=RerankerModelName.semantic_ranker_default_004,
        friendly_name="Semantic Ranker Default 004",
        providers=[
            KilnRerankerModelProvider(
                name=ModelProviderName.vertex,
                model_id="vertex_ai/semantic-ranker-default-004",
            ),
        ],
    ),
    # semantic-ranker-fast-004 (Vertex AI)
    KilnRerankerModel(
        family=KilnRerankerModelFamily.vertex_reranker,
        name=RerankerModelName.semantic_ranker_fast_004,
        friendly_name="Semantic Ranker Fast 004",
        providers=[
            KilnRerankerModelProvider(
                name=ModelProviderName.vertex,
                model_id="semantic-ranker-fast-004",
            ),
        ],
    ),
    # Amazon Rerank 1.0
    KilnRerankerModel(
        family=KilnRerankerModelFamily.amazon_rerank,
        name=RerankerModelName.amazon_rerank_1_0,
        friendly_name="Amazon Rerank 1.0",
        providers=[
            KilnRerankerModelProvider(
                name=ModelProviderName.amazon_bedrock,
                model_id="arn:aws:bedrock:us-west-2::foundation-model/amazon.rerank-v1:0",
            ),
        ],
    ),
]


def get_model_by_name(name: str | RerankerModelName) -> KilnRerankerModel:
    for model in built_in_rerankers:
        if model.name == name:
            return model
    raise ValueError(f"Reranker model {name} not found in the list of built-in models")


def built_in_reranker_models_from_provider(
    provider_name: ModelProviderName, model_name: str | RerankerModelName
) -> KilnRerankerModelProvider | None:
    for model in built_in_rerankers:
        if model.name == model_name:
            for p in model.providers:
                if p.name == provider_name:
                    return p
    return None
