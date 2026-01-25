from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SpecQuestionerInput")


@_attrs_define
class SpecQuestionerInput:
    """
    Attributes:
        task_prompt (str): The task's prompt
        specification (str): The specification to analyze
        task_input_schema (None | str | Unset): If the task's input must conform to a specific input schema, it will be
            provided here
        task_output_schema (None | str | Unset): If the task's output must conform to a specific schema, it will be
            provided here
    """

    task_prompt: str
    specification: str
    task_input_schema: None | str | Unset = UNSET
    task_output_schema: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        task_prompt = self.task_prompt

        specification = self.specification

        task_input_schema: None | str | Unset
        if isinstance(self.task_input_schema, Unset):
            task_input_schema = UNSET
        else:
            task_input_schema = self.task_input_schema

        task_output_schema: None | str | Unset
        if isinstance(self.task_output_schema, Unset):
            task_output_schema = UNSET
        else:
            task_output_schema = self.task_output_schema

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "task_prompt": task_prompt,
                "specification": specification,
            }
        )
        if task_input_schema is not UNSET:
            field_dict["task_input_schema"] = task_input_schema
        if task_output_schema is not UNSET:
            field_dict["task_output_schema"] = task_output_schema

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        task_prompt = d.pop("task_prompt")

        specification = d.pop("specification")

        def _parse_task_input_schema(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        task_input_schema = _parse_task_input_schema(d.pop("task_input_schema", UNSET))

        def _parse_task_output_schema(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        task_output_schema = _parse_task_output_schema(d.pop("task_output_schema", UNSET))

        spec_questioner_input = cls(
            task_prompt=task_prompt,
            specification=specification,
            task_input_schema=task_input_schema,
            task_output_schema=task_output_schema,
        )

        return spec_questioner_input
