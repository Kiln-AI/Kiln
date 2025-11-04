import asyncio
import os
import random
import string
import time
from pathlib import Path
from typing import List

import pytest

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    VectorStoreQuery as AdapterVectorStoreQuery,
)
from kiln_ai.adapters.vector_store.lancedb_adapter import LanceDBAdapter
from kiln_ai.adapters.vector_store.lancedb_helpers import (
    convert_to_llama_index_node,
    deterministic_chunk_id,
    lancedb_construct_from_config,
)
from kiln_ai.adapters.vector_store.vector_store_registry import (
    vector_store_adapter_for_config,
)
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig, VectorStoreType


def _random_text(n: int = 64) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits + " ", k=n))


def _make_configs() -> tuple[RagConfig, VectorStoreConfig]:
    rag = RagConfig(
        id="fake_rag_id",
        name="fake_rag_name",
        tool_name="fake_tool_name",
        tool_description="fake_tool_description",
        extractor_config_id="fake_extractor_config_id",
        chunker_config_id="fake_chunker_config_id",
        embedding_config_id="fake_embedding_config_id",
        vector_store_config_id="fake_vector_store_config_id",
    )
    vs = VectorStoreConfig(
        id="fake_vs_id",
        name="fake_vs_name",
        store_type=VectorStoreType.LANCE_DB_HYBRID,
        properties={
            "store_type": VectorStoreType.LANCE_DB_HYBRID,
            "overfetch_factor": 1,
            "vector_column_name": "vector",
            "text_key": "text",
            "doc_id_key": "doc_id",
            "similarity_top_k": 5,
            "nprobes": 10,
        },
    )
    return rag, vs


async def _seed(adapter: LanceDBAdapter, num_records: int = 1000) -> None:
    nodes = []
    for i in range(num_records):
        doc_id = f"doc-{i // 10}"
        node_id = deterministic_chunk_id(doc_id, i % 10)
        text = _random_text(128)
        # simple synthetic 128-dim unit vectors clustered by doc index
        dim = 64
        base = (i % 10) / 10.0
        vec = [base] * dim
        nodes.append(
            convert_to_llama_index_node(
                document_id=doc_id,
                chunk_idx=i % 10,
                node_id=node_id,
                text=text,
                vector=vec,
            )
        )
    if len(nodes):
        print(f"Adding {len(nodes)} nodes to database")
        await adapter.lancedb_vector_store.async_add(nodes)


async def _qps_driver(
    rag: RagConfig,
    vs: VectorStoreConfig,
    qps: int,
    duration_s: int,
) -> None:
    stop_at = time.time() + duration_s
    in_flight: List[asyncio.Task] = []
    start_time = time.time()
    completed = 0
    counter_lock = asyncio.Lock()

    async def one_query():
        nonlocal completed
        # hybrid: both embedding and text
        query_vec = [0.5] * 64
        query_text = "test"
        try:
            # Create a brand new adapter (and underlying LanceDBVectorStore) per request
            per_request_adapter = await vector_store_adapter_for_config(rag, vs)
            await per_request_adapter.search(
                query=AdapterVectorStoreQuery(
                    query_embedding=query_vec,
                    query_string=query_text,
                )
            )
        finally:
            async with counter_lock:
                completed += 1

    while time.time() < stop_at:
        tick_start = time.time()
        for _ in range(qps):
            in_flight.append(asyncio.create_task(one_query()))

        # progress report once per tick
        elapsed = max(time.time() - start_time, 1e-6)
        async with counter_lock:
            done = completed
        avg_qps = done / elapsed
        print(f"Progress: completed={done}, avg_qps={avg_qps:.2f}")

        # maintain 1-second pacing for this tick
        await asyncio.sleep(max(0.0, 1.0 - (time.time() - tick_start)))

    if in_flight:
        await asyncio.gather(*in_flight)

    # final report
    total_elapsed = max(time.time() - start_time, 1e-6)
    async with counter_lock:
        total_done = completed
    final_avg = total_done / total_elapsed
    print(f"Done: completed={total_done}, avg_qps={final_avg:.2f}")


@pytest.mark.paid
async def test_lancedb_concurrency_hammer() -> None:
    rag, vs = _make_configs()

    adapter = await vector_store_adapter_for_config(rag, vs)
    assert isinstance(adapter, LanceDBAdapter)

    # Ensure a fresh store instance
    target_path = adapter.lancedb_path_for_config(rag)
    ldb = lancedb_construct_from_config(vs, uri=target_path)
    adapter.lancedb_vector_store = ldb

    num_records = 100
    print(f"Seeding database with {num_records} records to {target_path}")
    await _seed(adapter, num_records=num_records)
    print(f"Seeded database with {num_records} records to {target_path}")

    # hammer at 50 qps for N minutes
    minutes = int(os.getenv("CONCURRENCY_TEST_MINUTES", 2))
    qps = int(os.getenv("CONCURRENCY_TEST_QPS", 500))
    print(f"Hammering at {qps} qps for {minutes} minutes")
    await _qps_driver(rag, vs, qps=qps, duration_s=minutes * 60)
    print(f"Hammered at {qps} qps for {minutes} minutes")
