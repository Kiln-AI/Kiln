from abc import ABC, abstractmethod
from typing import List, Tuple

from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.extraction import Extraction
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig


class BaseVectorStoreAdapter(ABC):
    def __init__(self, config: VectorStoreConfig):
        self.config = config

    @abstractmethod
    async def create_index(self, rag_config: RagConfig):
        """
        Create an index for the given RagConfig. What this means in practice will
        depend on the concrete vector store adapter. For LanceDB, this means creating a
        table with the given schema. Each RagConfig has its own isolated index because
        we obviously want to query within the context of a single config.
        """
        pass

    @abstractmethod
    async def upsert_chunks(
        self, chunks: List[Tuple[Extraction, ChunkedDocument, ChunkEmbeddings]]
    ):
        """
        Upsert documents into the index for the given RagConfig. The implementation
        must be idempotent.
        """
        # TODO: need to try a few ways to see which ones seem less heavy - as lancedb seems
        # to work like Elasticsearch and does something like flush out segments to disk and
        # then run compaction / merge periodically - in some storage systems, accumulating writes without
        # leaving it time to compact can degrade perf into oblivion (in my experience, elasticsearch
        # could get orders of magnitude slower when it had to do a full reindex one document at a time).
        # Some storage systems have a reindexing interface or bulk upsert; that usually can work better
        # for rapid fire write volume.
        pass

    @abstractmethod
    async def search(self, rag_config: RagConfig, query: str, k: int):
        pass

    def close(self):
        """
        Close the connection to the vector store. Default implementation does nothing.
        """
        pass
