from kiln_ai.adapters.provider_tools import finetune_from_id
from kiln_ai.datamodel.finetune import Finetune


def finetune_run_config_id(project_id: str, task_id: str, finetune_id: str) -> str:
    """
    Build in-memory ID for run-config inside a finetune. Format: finetune_run_config::project_id::task_id::finetune_id
    project_id::task_id::finetune_id is Finetune.model_id()
    """
    return f"finetune_run_config::{project_id}::{task_id}::{finetune_id}"


def finetune_from_finetune_run_config_id(finetune_run_config_id: str) -> Finetune:
    """
    Get the finetune from a finetune run config ID.
    """
    if not finetune_run_config_id.startswith("finetune_run_config::"):
        raise ValueError(
            f"Invalid finetune run config ID: {finetune_run_config_id}, expected format: finetune_run_config::project_id::task_id::finetune_id"
        )

    model_id = finetune_run_config_id.removeprefix("finetune_run_config::")
    return finetune_from_id(model_id)
