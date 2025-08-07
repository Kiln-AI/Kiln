from typing import List, Tuple

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    VectorStoreConfig,
)
from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.rag import RagConfig
from lancedb import AsyncConnection, AsyncTable
from lancedb.pydantic import LanceModel, Vector


class LanceDBAdapter(BaseVectorStoreAdapter):
    def __init__(self, config: VectorStoreConfig, connection: AsyncConnection):
        super().__init__(config)
        self.connection = connection
        self.config_properties = self.config.lancedb_typed_properties()

        # the adapter is not table-specific (as it can also destroy / create tables)
        # this is to keep a handle on the currently open table so we do not have to
        # open it every time
        self.active_table: AsyncTable | None = None

    def _lancedb_table_schema(self) -> type[LanceModel]:
        class ChunkLanceDBSchema(LanceModel):
            # not ideal, but this dynamic field creation seems to be the only way to
            # define the vector dimensionality
            document_id: str
            vector: Vector(dim=self.config_properties.vector_dimensions)  # type: ignore
            text: str

        return ChunkLanceDBSchema

    def _lancedb_table_name(self) -> str:
        return f"rag_config_{self.config.id}"

    async def _table(self) -> AsyncTable:
        if self.active_table is None or not self.active_table.is_open():
            self.active_table = await self.connection.open_table(
                self._lancedb_table_name()
            )
        return self.active_table

    async def create_index(self, rag_config: RagConfig):
        # close the active table if it is open
        if self.active_table is not None:
            self.active_table.close()
            self.active_table = None

        await self.connection.create_table(
            name=self._lancedb_table_name(),
            # by default, lancedb will raise an error if the table already exists
            exist_ok=True,
            # overwrite the table to ensure we start fresh - whether we set that on
            # totally depends on how fast it is
            mode="overwrite",
            schema=self._lancedb_table_schema(),
            # TODO: decide whether we want to insert data on creation or not
            # we could insert data on creation here: https://lancedb.github.io/lancedb/guides/tables/#from-list-of-tuples-or-dictionaries
            # in which case we would not need to specify the schema explicitly; however, in most cases, I imagine we will
            # create an empty table first, and then add data to it
            #
            # there also is a way to insert batches on creation: https://lancedb.github.io/lancedb/guides/tables/#using-iterators-writing-large-datasets
            # data=data,
        )

    async def upsert_chunks(
        self,
        chunks: List[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
    ):
        table = await self._table()

        # TODO: refactor this to upsert using an iterator instead (maybe)
        records = []
        for chunk in chunks:
            document_id, chunked_document, chunk_embeddings = chunk
            for chunk_text, chunk_vector in zip(
                chunked_document.chunks, chunk_embeddings.embeddings
            ):
                records.append(
                    {
                        "document_id": document_id,
                        "text": chunk_text,
                        "vector": chunk_vector,
                    }
                )

        await (
            table.merge_insert("document_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(records)
        )

    async def search(self, rag_config: RagConfig, query: str, k: int):
        pass
