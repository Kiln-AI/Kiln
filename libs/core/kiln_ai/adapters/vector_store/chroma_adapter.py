import logging
from typing import List, Sequence, Tuple

from chromadb import Collection, GetResult, Metadata
from chromadb.api import ClientAPI
from chromadb.api.collection_configuration import (
    CreateCollectionConfiguration,  # CreateHNSWConfiguration,
)
from chromadb.api.types import OneOrMany, QueryResult

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    BaseVectorStoreCollection,
    SearchResult,
    SimilarityMetric,
    VectorStoreConfig,
)
from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.rag import RagConfig

logger = logging.getLogger(__name__)


class ChromaAdapter(BaseVectorStoreAdapter):
    def __init__(
        self,
        vector_store_config: VectorStoreConfig,
        client: ClientAPI,
    ):
        super().__init__(vector_store_config)
        self.client = client
        self.config_properties = self.vector_store_config.chroma_typed_properties()

    async def create_collection(self, rag_config: RagConfig, vector_dimensions: int):
        chroma_collection = self.client.create_collection(
            name=self.table_name_for_rag_config(rag_config),
            configuration=CreateCollectionConfiguration(
                # HNSW documented here: https://docs.trychroma.com/docs/collections/configure#hnsw-index-configuration
                # TODO: for now we disable HNSW to avoid causing noise in tests
                # hnsw=CreateHNSWConfiguration(
                #     # TODO: get these from properties
                #     ef_construction=100,
                #     max_neighbors=100,
                #     space="cosine",  # cosine, l2, ip (Inner Product aka dot product)
                # ),
            ),
            # TODO: have test to see what it does if collection already exists
            # and this is False - does it throw or not
            get_or_create=False,
        )

        return ChromaCollection(
            vector_store_config=self.vector_store_config,
            chroma_collection=chroma_collection,
        )

    async def collection(
        self,
        rag_config: RagConfig,
    ) -> "ChromaCollection":
        return ChromaCollection(
            vector_store_config=self.vector_store_config,
            chroma_collection=self.client.get_collection(
                name=self.table_name_for_rag_config(rag_config)
            ),
        )

    async def destroy_collection(self, rag_config: RagConfig):
        self.client.delete_collection(name=self.table_name_for_rag_config(rag_config))

    def table_name_for_rag_config(self, rag_config: RagConfig) -> str:
        return f"rag_config_{rag_config.id}"


class ChromaCollection(BaseVectorStoreCollection):
    def __init__(
        self,
        vector_store_config: VectorStoreConfig,
        chroma_collection: Collection,
    ):
        super().__init__(vector_store_config)
        self.chroma_collection = chroma_collection

    def id_for_chunk(self, document_id: str, chunk_idx: int) -> str:
        return f"{document_id}::{chunk_idx}"

    async def upsert_chunks(
        self,
        chunks: List[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
    ):
        # TODO: upsert is good, but may be misused if people think that upserting
        # chunks will overwrite whatever chunks there were before for that document,
        # in the case where the new chunks are fewer than the old chunks, there will
        # be lingering old chunks that never get deleted
        # maybe something to somehow make explicit, or expose a delete document method
        ids: List[str] = []
        embeddings: List[Sequence[float]] = []
        documents: List[str] = []
        metadatas: OneOrMany[Metadata] = []
        for document_id, chunked_document, chunk_embeddings in chunks:
            chunk_texts = await chunked_document.load_chunks_text()
            for chunk_idx, (chunk_text, embedding) in enumerate(
                zip(chunk_texts, chunk_embeddings.embeddings)
            ):
                ids.append(self.id_for_chunk(document_id, chunk_idx))
                embeddings.append(embedding.vector)
                documents.append(chunk_text)
                metadatas.append(
                    {
                        "document_id": document_id,
                        "chunk_idx": chunk_idx,
                    }
                )

        self.chroma_collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def parse_record_metadata(self, metadata: Metadata) -> Tuple[str, int]:
        # Chroma lets us store metadata as a string, but it is best to keep it as a dictionary
        # we still take in string as a possible type in the args otherwise typechecking breaks
        if isinstance(metadata, str):
            raise RuntimeError("Metadata should be stored as a dictionary")

        doc_id = metadata.get("document_id")
        if not isinstance(doc_id, str):
            raise RuntimeError("Document id is not a string")

        chunk_idx = metadata.get("chunk_idx")
        if not isinstance(chunk_idx, int):
            raise RuntimeError("Chunk index is not an integer")

        return doc_id, chunk_idx

    def map_fts_search_results(
        self, chrome_query_results: GetResult
    ) -> List[SearchResult]:
        ids = chrome_query_results.get("ids", [])
        if ids is None or len(ids) == 0:
            return []

        texts = chrome_query_results.get("documents", [])
        if texts is None or len(texts) == 0:
            raise RuntimeError("No documents found in query results")

        metadatas = chrome_query_results.get("metadatas", [])
        if metadatas is None or len(metadatas) == 0:
            raise RuntimeError("No metadatas found in query results")

        results: List[SearchResult] = []
        for text, metadata in zip(texts, metadatas):
            doc_id, chunk_idx = self.parse_record_metadata(metadata)
            results.append(
                SearchResult(
                    document_id=doc_id,
                    chunk_idx=chunk_idx,
                    chunk_text=text,
                    score=None,
                )
            )
        return results

    def map_vector_search_results(
        self, chrome_query_results: QueryResult | GetResult
    ) -> List[SearchResult]:
        ids = chrome_query_results.get("ids", [])
        if ids is None or len(ids) == 0:
            return []

        texts = chrome_query_results.get("documents", [])
        if texts is None or len(texts) == 0:
            raise RuntimeError("No documents found in query results")
        else:
            texts = texts[0]

        metadatas = chrome_query_results.get("metadatas", [])
        if metadatas is None or len(metadatas) == 0:
            raise RuntimeError("No metadatas found in query results")
        else:
            metadatas = metadatas[0]

        # only QueryResult has distances (vector search)
        scores: Sequence[float | None] = []
        distances = chrome_query_results.get("distances")
        if distances is not None and isinstance(distances, list) and len(distances) > 0:
            scores = distances[0]

        results: List[SearchResult] = []
        for text, score, metadata in zip(texts, scores, metadatas):
            doc_id, chunk_idx = self.parse_record_metadata(metadata)  # type: ignore
            results.append(
                SearchResult(
                    document_id=doc_id,
                    chunk_idx=chunk_idx,
                    chunk_text=text,
                    score=score,
                )
            )
        return results

    async def search_fts(self, query: str, k: int) -> List[SearchResult]:
        # TODO: need to check what they store in inverted index and if they tokenize
        # for a specific language
        #
        # FTS on Chroma only seems to support substring matching (exact, case sensitive)
        # If we want something more sophisticated (e.g. stop word, ngram, tokenization, lemmatization, etc.)
        # we should preprocess the query ourselves
        results = self.chroma_collection.get(
            where_document={"$contains": query}, limit=k
        )
        return self.map_fts_search_results(results)

    async def search_vector(
        self,
        vector: List[float],
        k: int,
        distance_type: SimilarityMetric,
    ) -> List[SearchResult]:
        # shape:
        # {
        #   'ids': [['doc_002_1']],
        #   'embeddings': None,
        #   'documents': [['The area of New York City, USA is approximately 783.8 square kilometers']],
        #   'uris': None,
        #   'included': ['metadatas', 'documents', 'distances'],
        #   'data': None,
        #   'metadatas': [[None]], 'distances': [[2.0]]
        # }
        results = self.chroma_collection.query(
            query_embeddings=[vector],
            n_results=k,
        )
        return self.map_vector_search_results(results)

    async def count_records(self) -> int:
        return self.chroma_collection.count()

    async def optimize(self):
        # TODO: chromadb does not seem to need to be manually forced to refresh index, compact, etc.
        # but need to double check
        pass

    async def close(self):
        # chromadb does not have a close method, so we don't need to do anything
        pass
