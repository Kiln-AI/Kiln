from enum import Enum
from typing import TYPE_CHECKING, Any, Union, cast

from pydantic import Field, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    NAME_FIELD,
    KilnAttachmentModel,
    KilnParentedModel,
)

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class OutputFormat(str, Enum):
    TEXT = "text/plain"
    MARKDOWN = "text/markdown"


class ExtractorType(str, Enum):
    gemini = "gemini"


class Kind(str, Enum):
    DOCUMENT = "document"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


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
        if self.extractor_type == ExtractorType.gemini:
            validate_prompt_for_kind(self.properties.get("prompt_for_kind"))
            validate_model_name(self.properties.get("model_name"))
            return self
        else:
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
