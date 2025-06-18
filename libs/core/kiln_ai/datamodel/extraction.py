import logging
from enum import Enum
from typing import TYPE_CHECKING, Any, List, Union

import anyio
from pydantic import (
    BaseModel,
    Field,
    SerializationInfo,
    field_serializer,
    model_validator,
)
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    NAME_FIELD,
    KilnAttachmentModel,
    KilnParentedModel,
    KilnParentModel,
)

logger = logging.getLogger(__name__)

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


def validate_prompt(prompt: Any, name: str):
    if not isinstance(prompt, str):
        raise ValueError(f"{name} must be a string.")
    if prompt == "":
        raise ValueError(f"{name} cannot be empty.")


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

    async def output_content(self) -> str | None:
        if not self.output.is_persisted:
            return None
        if not self.path:
            raise ValueError(
                "Failed to resolve the path of extraction output attachment because the extraction does not have a path."
            )

        full_path = self.output.resolve_path(self.path.parent)

        try:
            return await anyio.Path(full_path).read_text(encoding="utf-8")
        except Exception as e:
            logger.error(
                f"Failed to read extraction output for {full_path}: {e}", exc_info=True
            )
            raise ValueError(f"Failed to read extraction output: {e}")


class ExtractorConfig(KilnParentedModel):
    name: str = NAME_FIELD
    is_archived: bool = Field(
        default=False,
        description="Whether the extractor config is archived. Archived extractor configs are not shown in the UI and are not available for use.",
    )
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
    properties: dict[str, str | int | float | bool | dict[str, str] | None] = Field(
        default_factory=dict,
        description="Properties to be used to execute the extractor config. This is extractor_type specific and should serialize to a json dict.",
    )

    @model_validator(mode="after")
    def validate_properties(self) -> Self:
        if self.extractor_type == ExtractorType.GEMINI:
            validate_model_name(self.properties.get("model_name"))
            validate_prompt(self.properties.get("prompt_document"), "prompt_document")
            validate_prompt(self.properties.get("prompt_video"), "prompt_video")
            validate_prompt(self.properties.get("prompt_audio"), "prompt_audio")
            validate_prompt(self.properties.get("prompt_image"), "prompt_image")
            return self
        raise ValueError(f"Invalid extractor type: {self.extractor_type}")

    def model_name(self) -> str | None:
        model_name = self.properties.get("model_name")
        if model_name is None:
            return None
        if not isinstance(model_name, str):
            raise ValueError("Invalid model_name. model_name must be a string.")
        return model_name

    def prompt_document(self) -> str | None:
        prompt = self.properties.get("prompt_document")
        if prompt is None:
            return None
        if not isinstance(prompt, str):
            raise ValueError(
                "Invalid prompt_document. prompt_document must be a string."
            )
        return prompt

    def prompt_video(self) -> str | None:
        prompt = self.properties.get("prompt_video")
        if prompt is None:
            return None
        if not isinstance(prompt, str):
            raise ValueError("Invalid prompt_video. prompt_video must be a string.")
        return prompt

    def prompt_audio(self) -> str | None:
        prompt = self.properties.get("prompt_audio")
        if prompt is None:
            return None
        if not isinstance(prompt, str):
            raise ValueError("Invalid prompt_audio. prompt_audio must be a string.")
        return prompt

    def prompt_image(self) -> str | None:
        prompt = self.properties.get("prompt_image")
        if prompt is None:
            return None
        if not isinstance(prompt, str):
            raise ValueError("Invalid prompt_image. prompt_image must be a string.")
        return prompt

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

    @field_serializer("attachment")
    def serialize_attachment(
        self, attachment: KilnAttachmentModel, info: SerializationInfo
    ) -> dict:
        context = info.context or {}
        context["filename_prefix"] = "attachment"
        return attachment.model_dump(mode="json", context=context)


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
