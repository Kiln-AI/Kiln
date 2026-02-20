from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TaskInfo")


@_attrs_define
class TaskInfo:
    """Shared information about a task

    Attributes:
        task_prompt (str):
        task_input_schema (None | str | Unset):
        task_output_schema (None | str | Unset):
    """

    task_prompt: str
    task_input_schema: None | str | Unset = UNSET
    task_output_schema: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_prompt = self.task_prompt

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
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_prompt": task_prompt,
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

        task_info = cls(
            task_prompt=task_prompt,
            task_input_schema=task_input_schema,
            task_output_schema=task_output_schema,
        )

        task_info.additional_properties = d
        return task_info

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
