from enum import Enum
from typing import TYPE_CHECKING, Any, List, Union, cast

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    NAME_FIELD,
    KilnAttachmentModel,
    KilnParentedModel,
    KilnParentModel,
)

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class Kind(str, Enum):
    DOCUMENT = "document"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class OutputFormat(str, Enum):
    TEXT = "text/plain"
    MARKDOWN = "text/markdown"


class ExtractorType(str, Enum):
    GEMINI = "gemini"


def validate_prompt_for_kind(prompt_for_kind: Any):
    # check prompt_for_kind is a dictionary
    if not isinstance(prompt_for_kind, dict):
        raise ValueError("prompt_for_kind must be a dictionary.")
    # check all keys are valid kinds
    for key, value in prompt_for_kind.items():
        # raise an error if the key is not a valid kind
        try:
            Kind(key)
        except ValueError:
            raise ValueError(f"Invalid kind in prompt_for_kind: '{key}'")
        # type the key to a kind
        if not isinstance(value, str):
            raise ValueError(
                f"Invalid prompt for kind: '{key}'. Prompt must be a string."
            )

    # check all kinds are present
    for kind in Kind:
        if kind not in prompt_for_kind:
            raise ValueError(
                f"Missing prompt for kind: '{kind.value}'. All kinds must be present in prompt_for_kind."
            )


def validate_model_name(model_name: Any):
    if not isinstance(model_name, str):
        raise ValueError("model_name must be a string.")
    if model_name == "":
        raise ValueError("model_name cannot be empty.")


class ExtractionSource(str, Enum):
    PROCESSED = "processed"
    PASSTHROUGH = "passthrough"


class Extraction(KilnParentedModel):
    source: ExtractionSource = Field(
        description="The source of the extraction.",
    )
    extractor_config_id: ID_TYPE = Field(
        description="The ID of the extractor config that was used to extract the data.",
    )
    output: KilnAttachmentModel = Field(
        description="The extraction output.",
    )

    def parent_document(self) -> Union["Document", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Document":
            return None
        return self.parent  # type: ignore

    def output_content(self) -> str | None:
        if not self.output.is_persisted:
            return None
        if not self.path:
            raise ValueError(
                "Failed to resolve the path of extraction output attachment because the extraction does not have a path."
            )

        full_path = self.output.resolve_path(self.path.parent)
        with open(full_path, "r") as f:
            return f.read()


class ExtractorConfig(KilnParentedModel):
    name: str = NAME_FIELD
    description: str | None = Field(
        default=None, description="The description of the extractor config"
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.MARKDOWN,
        description="The format to use for the output.",
    )
    passthrough_mimetypes: list[OutputFormat] = Field(
        default_factory=list,
        description="If the mimetype is in this list, the extractor will not be used and the text content of the file will be returned as is.",
    )
    extractor_type: ExtractorType = Field(
        description="This is used to determine the type of extractor to use.",
    )
    properties: dict[str, str | int | float | bool | dict[str, str]] = Field(
        default={},
        description="Properties to be used to execute the extractor config. This is extractor_type specific and should serialize to a json dict.",
    )

    @model_validator(mode="after")
    def validate_properties(self) -> Self:
        if self.extractor_type == ExtractorType.GEMINI:
            validate_prompt_for_kind(self.properties.get("prompt_for_kind"))
            validate_model_name(self.properties.get("model_name"))
            return self
        raise ValueError(f"Invalid extractor type: {self.extractor_type}")

    def model_name(self) -> str | None:
        model_name = self.properties.get("model_name")
        if model_name is None:
            return None
        if not isinstance(model_name, str):
            raise ValueError("Invalid model_name. model_name must be a string.")
        return model_name

    def prompt_for_kind(self) -> dict[Kind, str] | None:
        prompt_for_kind = self.properties.get("prompt_for_kind")
        if prompt_for_kind is None:
            return None
        if not isinstance(prompt_for_kind, dict):
            raise ValueError(
                "Invalid prompt_for_kind. prompt_for_kind must be a dictionary."
            )
        return cast(dict[Kind, str], prompt_for_kind)

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore


class FileInfo(BaseModel):
    filename: str = Field(description="The filename of the file")

    size: int = Field(description="The size of the file in bytes")

    mime_type: str = Field(description="The MIME type of the file")

    attachment: KilnAttachmentModel = Field(
        description="The attachment to the file",
    )


class Document(
    KilnParentedModel, KilnParentModel, parent_of={"extractions": Extraction}
):
    name: str = NAME_FIELD

    description: str = Field(description="A description for the file")

    original_file: FileInfo = Field(description="The original file")

    # TODO: move {mime_type:kind} mapping out of GeminiExtractor and into here
    #   - will also need to have models specify which mimetypes they support
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
