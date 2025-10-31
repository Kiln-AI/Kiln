import logging
from enum import Enum
from typing import TYPE_CHECKING, List, Literal, Union

import anyio
from pydantic import (
    BaseModel,
    Field,
    SerializationInfo,
    ValidationInfo,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)
from typing_extensions import Self, TypedDict

from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    FilenameString,
    KilnAttachmentModel,
    KilnParentedModel,
    KilnParentModel,
)
from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.utils.validation import NonEmptyString

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project

logger = logging.getLogger(__name__)


class Kind(str, Enum):
    DOCUMENT = "document"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class OutputFormat(str, Enum):
    TEXT = "text/plain"
    MARKDOWN = "text/markdown"


class ExtractorType(str, Enum):
    LITELLM = "litellm"


SUPPORTED_MIME_TYPES = {
    Kind.DOCUMENT: {
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/html",
        "text/md",
    },
    Kind.IMAGE: {
        "image/png",
        "image/jpeg",
    },
    Kind.VIDEO: {
        "video/mp4",
        "video/quicktime",
    },
    Kind.AUDIO: {
        "audio/wav",
        "audio/mpeg",
        "audio/ogg",
    },
}


class ExtractionModel(BaseModel):
    name: str
    label: str


class ExtractionSource(str, Enum):
    PROCESSED = "processed"
    PASSTHROUGH = "passthrough"


class Extraction(
    KilnParentedModel, KilnParentModel, parent_of={"chunked_documents": ChunkedDocument}
):
    source: ExtractionSource = Field(
        description="The source of the extraction.",
    )
    extractor_config_id: ID_TYPE = Field(
        description="The ID of the extractor config used to extract the data.",
    )
    output: KilnAttachmentModel = Field(
        description="The extraction output.",
    )

    def parent_document(self) -> Union["Document", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Document":
            return None
        return self.parent  # type: ignore

    async def output_content(self) -> str | None:
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

    def chunked_documents(self, readonly: bool = False) -> list[ChunkedDocument]:
        return super().chunked_documents(readonly=readonly)  # type: ignore


class LitellmExtractorConfigProperties(TypedDict, total=True):
    extractor_type: Literal[ExtractorType.LITELLM]
    prompt_document: NonEmptyString
    prompt_image: NonEmptyString
    prompt_video: NonEmptyString
    prompt_audio: NonEmptyString


class ExtractorConfig(KilnParentedModel):
    name: FilenameString = Field(
        description="A name to identify the extractor config.",
    )
    is_archived: bool = Field(
        default=False,
        description="Whether the extractor config is archived. Archived extractor configs are not shown in the UI and are not available for use.",
    )
    description: str | None = Field(
        default=None, description="The description of the extractor config"
    )
    model_provider_name: str = Field(
        description="The name of the model provider to use for the extractor config.",
    )
    model_name: str = Field(
        description="The name of the model to use for the extractor config.",
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
    properties: LitellmExtractorConfigProperties = Field(
        description="Properties to be used to execute the extractor config. This is extractor_type specific and should serialize to a json dict.",
        # the discriminator refers to the properties->extractor_type key (not the extractor_type field on the parent model)
        discriminator="extractor_type",
    )

    @model_validator(mode="before")
    def upgrade_missing_discriminator_properties(
        cls, data: dict, info: ValidationInfo
    ) -> dict:
        if not info.context or not info.context.get("loading_from_file", False):
            # Not loading from file, so no need to upgrade
            return data

        if not isinstance(data, dict):
            return data

        # backward compatibility:
        # - we originally did not have the extractor_type in the properties, so we need to add it here
        # - we started wanted to have extractor_type in the properties to use pydantic's discriminated union feature
        properties = data.get("properties", {})
        if "extractor_type" not in properties:
            # the extractor_type on the parent model is always there, we just need to add it to the properties
            properties["extractor_type"] = data["extractor_type"]
            data["properties"] = properties
        return data

    @model_validator(mode="after")
    def ensure_extractor_type_matches_properties(self):
        # sanity check to ensure the extractor_type matches the properties extractor_type
        if self.extractor_type != self.properties["extractor_type"]:
            raise ValueError(
                f"Extractor type mismatch: {self.extractor_type} != {self.properties['extractor_type']}. This is a bug, please report it."
            )
        return self

    @property
    def litellm_properties(self) -> LitellmExtractorConfigProperties:
        if self.properties["extractor_type"] != ExtractorType.LITELLM:
            raise ValueError(
                f"Litellm properties are only available for litellm extractor type. Got {self.properties.get('extractor_type')}"
            )
        return self.properties

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

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, mime_type: str, info: ValidationInfo) -> str:
        filename = info.data.get("filename") or ""

        for mime_types in SUPPORTED_MIME_TYPES.values():
            if mime_type in mime_types:
                return mime_type
        raise ValueError(f"MIME type is not supported: {mime_type} (for {filename})")


class Document(
    KilnParentedModel, KilnParentModel, parent_of={"extractions": Extraction}
):
    # this field should not be changed after creation
    name: FilenameString = Field(
        description="A name to identify the document.",
    )

    # this field can be changed after creation
    name_override: str | None = Field(
        description="A friendly name to identify the document. This is used for display purposes and can be different from the name.",
        default=None,
    )

    description: str = Field(description="A description for the file")

    original_file: FileInfo = Field(description="The original file")

    kind: Kind = Field(
        description="The kind of document. The kind is a broad family of filetypes that can be handled in a similar way"
    )

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

    def extractions(self, readonly: bool = False) -> list[Extraction]:
        return super().extractions(readonly=readonly)  # type: ignore

    @computed_field
    @property
    def friendly_name(self) -> str:
        # backward compatibility: old documents did not have name_override
        return self.name_override or self.name


def get_kind_from_mime_type(mime_type: str) -> Kind | None:
    for kind, mime_types in SUPPORTED_MIME_TYPES.items():
        if mime_type in mime_types:
            return kind
    return None
