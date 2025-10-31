from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from kiln_ai.datamodel.datamodel_enums import ModelProviderName


class KilnRerankerModelFamily(str, Enum):
    """
    Enumeration of supported reranker model families.
    """

    llama_rank = "llama_rank"


class RerankerModelName(str, Enum):
    """
    Enumeration of specific model versions supported by the system.
    """

    llama_rank = "llama_rank"


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
