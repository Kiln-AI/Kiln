from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="TargetTaskInfo")


@_attrs_define
class TargetTaskInfo:
    """
    Attributes:
        target_task_prompt (str): The Target Task prompt
        target_task_input_schema (str): JSON schema for the Target Task inputs
        target_task_output_schema (str): JSON schema for the Target Task outputs
    """

    target_task_prompt: str
    target_task_input_schema: str
    target_task_output_schema: str

    def to_dict(self) -> dict[str, Any]:
        target_task_prompt = self.target_task_prompt

        target_task_input_schema = self.target_task_input_schema

        target_task_output_schema = self.target_task_output_schema

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "target_task_prompt": target_task_prompt,
                "target_task_input_schema": target_task_input_schema,
                "target_task_output_schema": target_task_output_schema,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        target_task_prompt = d.pop("target_task_prompt")

        target_task_input_schema = d.pop("target_task_input_schema")

        target_task_output_schema = d.pop("target_task_output_schema")

        target_task_info = cls(
            target_task_prompt=target_task_prompt,
            target_task_input_schema=target_task_input_schema,
            target_task_output_schema=target_task_output_schema,
        )

        return target_task_info
