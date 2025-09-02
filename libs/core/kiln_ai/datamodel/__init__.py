"""
See our docs for details about our datamodel classes and hierarchy:

Developer docs: https://kiln-ai.github.io/Kiln/kiln_core_docs/kiln_ai.html

User docs: https://docs.kiln.tech/developers/kiln-datamodel
"""

# This component uses "flat" imports so we don't have too much internal structure exposed in the API.
# for example you can just `from datamodel import Task, Project` instead of `from datamodel.task import Task; from datamodel.project import Project`

from __future__ import annotations

from kiln_ai.datamodel import dataset_split, eval, strict_mode
from kiln_ai.datamodel.datamodel_enums import (
    FineTuneStatusType,
    Priority,
    StructuredOutputMode,
    TaskOutputRatingType,
)
from kiln_ai.datamodel.dataset_split import (
    DatasetSplit,
    DatasetSplitDefinition,
)
from kiln_ai.datamodel.external_tool_server import ExternalToolServer
from kiln_ai.datamodel.finetune import (
    Finetune,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.prompt import BasePrompt, Prompt
from kiln_ai.datamodel.prompt_id import (
    PromptGenerators,
    PromptId,
    prompt_generator_values,
)
from kiln_ai.datamodel.task import Task, TaskRequirement
from kiln_ai.datamodel.task_output import (
    DataSource,
    DataSourceProperty,
    DataSourceType,
    RequirementRating,
    TaskOutput,
    TaskOutputRating,
)
from kiln_ai.datamodel.task_run import (
    TaskRun,
    Usage,
)

__all__ = [
    "BasePrompt",
    "DataSource",
    "DataSourceProperty",
    "DataSourceType",
    "DatasetSplit",
    "DatasetSplitDefinition",
    "ExternalToolServer",
    "FineTuneStatusType",
    "Finetune",
    "Priority",
    "Project",
    "Prompt",
    "PromptGenerators",
    "PromptId",
    "RequirementRating",
    "StructuredOutputMode",
    "Task",
    "TaskOutput",
    "TaskOutputRating",
    "TaskOutputRatingType",
    "TaskRequirement",
    "TaskRequirement",
    "TaskRun",
    "Usage",
    "dataset_split",
    "eval",
    "prompt_generator_values",
    "strict_mode",
]
