from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Discriminator, Field, Tag, field_validator


class JinjaInputTransform(BaseModel):
    """Render the task input via a Jinja2 template, producing the first user
    message sent to the model. See specs/projects/templates/functional_spec.md
    for the full contract.
    """

    type: Literal["jinja"] = "jinja"
    template: str = Field(
        description="Jinja2 template source. Validated at save time.",
    )

    @field_validator("template")
    @classmethod
    def validate_template_compiles(cls, v: str) -> str:
        from kiln_ai.utils.jinja_engine import compile_template_or_raise

        compile_template_or_raise(v)
        return v


def _get_input_transform_type(data: Any) -> str | None:
    if isinstance(data, dict):
        return data.get("type")
    return getattr(data, "type", None)


InputTransform = Annotated[
    Union[Annotated[JinjaInputTransform, Tag("jinja")],],
    Discriminator(_get_input_transform_type),
]
