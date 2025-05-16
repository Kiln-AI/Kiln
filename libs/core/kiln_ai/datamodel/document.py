from typing import TYPE_CHECKING, List, Union

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import NAME_FIELD, KilnParentedModel, KilnParentModel
from kiln_ai.datamodel.extraction import Extraction, Kind

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class FileInfo(BaseModel):
    filename: str = Field(description="The filename of the file")

    size: int = Field(description="The size of the file in bytes")

    mime_type: str = Field(description="The MIME type of the file")

    # TODO: add attachment
    # attachment: KilnModelAttachment = Field(
    #     description="The attachment to the file",
    # )


class Document(
    KilnParentedModel, KilnParentModel, parent_of={"extractions": Extraction}
):
    name: str = NAME_FIELD

    description: str = Field(description="A description for the file")

    original_file: FileInfo = Field(description="The original file")

    # TODO: move {mime_type:kind} mapping out of GeminiExtractor and into here
    #   - will also need to have models specify which mimetypes they support
    # TODO: move Kind enum into this file (instead of in extraction.py)
    #   - waiting for ExtractionConfig PR merged to do this
    kind: Kind = Field(
        description="The kind of document. The kind is a broad family of filetypes that can be handled in a similar way"
    )

    # NOTE: could extract {tags + validate_tags} into a reusable Taggable model and inherit from that here
    # and in TaskRun
    # thoughts?
    tags: List[str] = Field(
        default_factory=list,
        description="Tags for the document. Tags are used to categorize documents for filtering and reporting.",
    )

    @model_validator(mode="after")
    def validate_tags(self) -> Self:
        for tag in self.tags:
            if not tag:
                raise ValueError("Tags cannot be empty strings")
            if " " in tag:
                raise ValueError("Tags cannot contain spaces. Try underscores.")

        return self

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore

    def extractions(self) -> list[Extraction]:
        return super().extractions()  # type: ignore
