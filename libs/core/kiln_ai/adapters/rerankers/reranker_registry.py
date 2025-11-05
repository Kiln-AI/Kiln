from kiln_ai.adapters.rerankers.base_reranker import BaseReranker
from kiln_ai.adapters.rerankers.litellm_reranker_adapter import LitellmRerankerAdapter
from kiln_ai.datamodel.reranker import RerankerConfig, RerankerType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def reranker_adapter_from_config(
    reranker_config: RerankerConfig,
) -> BaseReranker:
    match reranker_config.properties["type"]:
        case RerankerType.COHERE_COMPATIBLE:
            return LitellmRerankerAdapter(
                reranker_config,
            )
        case _:
            raise_exhaustive_enum_error(reranker_config.properties["type"])
