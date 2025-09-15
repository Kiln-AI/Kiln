import logging
from typing import Dict

from kiln_ai.adapters.rag.helpers import build_rag_workflow_runner
from kiln_ai.adapters.rag.rag_runners import RagStepRunnerProgress, RagWorkflowStepNames
from kiln_ai.adapters.vector_store.vector_store_registry import (
    vector_store_adapter_for_config,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig

logger = logging.getLogger(__name__)


async def count_records_in_vector_store(
    rag_config: RagConfig,
    vector_store_config: VectorStoreConfig,
) -> int:
    vector_store = await vector_store_adapter_for_config(
        rag_config, vector_store_config
    )
    count = await vector_store.count_records()
    return count


async def count_records_in_vector_store_for_rag_config(
    project: Project,
    rag_config: RagConfig,
) -> int:
    vector_store_config = VectorStoreConfig.from_id_and_parent_path(
        str(rag_config.vector_store_config_id),
        project.path,
    )
    if vector_store_config is None:
        raise ValueError(f"Rag config {rag_config.id} has no vector store config")
    return await count_records_in_vector_store(rag_config, vector_store_config)


async def compute_current_progress_for_rag_configs(
    project: Project,
    rag_configs: list[RagConfig],
) -> Dict[str, Dict[RagWorkflowStepNames, RagStepRunnerProgress]]:
    config_progress = {}
    for rag_config in rag_configs:
        if rag_config.id is None:
            raise ValueError(f"Rag config {rag_config.id} has no id")
        runner = build_rag_workflow_runner(project, rag_config.id)
        step_progresses = await runner.compute_current_counts()
        step_progress_map = {
            step_progress.step_name: step_progress for step_progress in step_progresses
        }
        config_progress[str(rag_config.id)] = step_progress_map
    return config_progress


async def compute_current_progress_for_rag_config(
    project: Project,
    rag_config: RagConfig,
) -> Dict[RagWorkflowStepNames, RagStepRunnerProgress]:
    config_progress = await compute_current_progress_for_rag_configs(
        project, [rag_config]
    )
    if rag_config.id not in config_progress:
        raise ValueError(f"Failed to compute progress for rag config {rag_config.id}")

    return config_progress[rag_config.id]
