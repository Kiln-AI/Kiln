from abc import ABC, abstractmethod

from kiln_ai.datamodel.reranker import RerankerConfig
from pydantic import BaseModel, Field, NonNegativeInt


class RerankDocument(BaseModel):
    id: str = Field(
        description="The id of the document. It has no particular meaning, it is just to identify the document after reranking."
    )
    text: str = Field(
        description="The text of the document. This is the content of the document that will be used for reranking."
    )


class RerankResult(BaseModel):
    index: NonNegativeInt = Field(
        description="The index of the reranked document in the original list of documents."
    )
    document: RerankDocument = Field(description="The reranked document.")
    relevance_score: float = Field(description="The relevance score of the document.")


class RerankResponse(BaseModel):
    results: list[RerankResult] = Field(description="The results of the reranking.")


class BaseReranker(ABC):
    """
    Base class for all rerankers.
    """

    def __init__(self, reranker_config: RerankerConfig):
        self.reranker_config = reranker_config

    @abstractmethod
    async def rerank(
        self, query: str, documents: list[RerankDocument]
    ) -> RerankResponse:
        """
        Rerank the documents based on the query.
        """
        pass
