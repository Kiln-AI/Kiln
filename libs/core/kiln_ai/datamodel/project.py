from pydantic import Field

from kiln_ai.datamodel.basemodel import NAME_FIELD, KilnParentModel
from kiln_ai.datamodel.chunk import ChunkerConfig
from kiln_ai.datamodel.extraction import Document, ExtractorConfig
from kiln_ai.datamodel.task import Task


class Project(
    KilnParentModel,
    parent_of={
        "tasks": Task,
        "documents": Document,
        "extractor_configs": ExtractorConfig,
        "chunker_configs": ChunkerConfig,
    },
):
    """
    A collection of related tasks.

    Projects organize tasks into logical groups and provide high-level descriptions
    of the overall goals.
    """

    name: str = NAME_FIELD
    description: str | None = Field(
        default=None,
        description="A description of the project for you and your team. Will not be used in prompts/training/validation.",
    )

    # Needed for typechecking. TODO P2: fix this in KilnParentModel
    def tasks(self) -> list[Task]:
        return super().tasks()  # type: ignore

    def documents(self, readonly: bool = False) -> list[Document]:
        return super().documents(readonly=readonly)  # type: ignore

    def extractor_configs(self, readonly: bool = False) -> list[ExtractorConfig]:
        return super().extractor_configs(readonly=readonly)  # type: ignore

    def chunker_configs(self, readonly: bool = False) -> list[ChunkerConfig]:
        return super().chunker_configs(readonly=readonly)  # type: ignore
