import json
from enum import Enum
from typing import Any, List

from pydantic import BaseModel, Field, ValidationError, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import NAME_FIELD, KilnBaseModel


def format_properties_errors(e: ValidationError) -> str:
    errors: List[str] = []
    for error in e.errors():
        loc = error["loc"][0]
        msg = error["msg"]
        errors.append(f"{loc}: {msg}.")
    return "\n".join(errors)


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


class GeminiProperties(BaseModel):
    prompt_for_kind: dict[Kind, str] = Field(
        description="A dictionary of prompts for each kind of content to extract.",
    )

    model_name: str = Field(
        description="The name of the model to use for this extractor config. ",
    )


class ExtractorConfig(KilnBaseModel):
    name: str = NAME_FIELD

    output_format: OutputFormat = Field(
        default=OutputFormat.MARKDOWN,
        description="The format to use for the output.",
    )
    passthrough_mimetypes: list[OutputFormat] = Field(
        default_factory=list,
        description="If the mimetype is in this list, the extractor will not be used and the text content of the file will be returned as is.",
    )
    extractor_type: ExtractorType = Field(
        default=ExtractorType.gemini,
        description="This is used to determine the type of extractor to use.",
    )
    properties: dict[str, Any] = Field(
        default={},
        description="Properties to be used to execute the extractor config. This is config_type specific and should serialize to a json dict.",
    )

    @model_validator(mode="after")
    def validate_properties(self) -> Self:
        if self.extractor_type == ExtractorType.gemini:
            # This will raise an error if the properties are invalid
            try:
                GeminiProperties(**self.properties)
            except ValidationError as e:
                raise ValueError(format_properties_errors(e))
            return self
        else:
            raise ValueError(f"Invalid extractor type: {self.extractor_type}")

    @model_validator(mode="after")
    def validate_json_serializable(self) -> Self:
        try:
            # This will raise a TypeError if the dict contains non-JSON-serializable objects
            json.dumps(self.properties)
        except TypeError as e:
            raise ValueError(f"Properties must be JSON serializable: {str(e)}")
        return self

    def gemini_properties(self) -> GeminiProperties:
        return GeminiProperties(**self.properties)
