from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="BatchPlanInput")


@_attrs_define
class BatchPlanInput:
    """Request payload for the batch planner copilot.

    Attributes:
        task_prompt (str): The target task's runtime system prompt (what the inputs are used for).
        count (int): Number of inputs to plan; the planner returns one prompt per input.
        task_input_schema (None | str | Unset): The target task's input JSON schema, if its inputs are structured.
        task_output_schema (None | str | Unset): The target task's output JSON schema, used for coverage/realism context
            only.
        input_data_guide (None | str | Unset): The target task's input data guide (input profile), if available.
        user_guidance (str | Unset): User guidance describing this batch (distribution, focus, edge cases). Default: ''.
    """

    task_prompt: str
    count: int
    task_input_schema: None | str | Unset = UNSET
    task_output_schema: None | str | Unset = UNSET
    input_data_guide: None | str | Unset = UNSET
    user_guidance: str | Unset = ""
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_prompt = self.task_prompt

        count = self.count

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

        input_data_guide: None | str | Unset
        if isinstance(self.input_data_guide, Unset):
            input_data_guide = UNSET
        else:
            input_data_guide = self.input_data_guide

        user_guidance = self.user_guidance

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_prompt": task_prompt,
                "count": count,
            }
        )
        if task_input_schema is not UNSET:
            field_dict["task_input_schema"] = task_input_schema
        if task_output_schema is not UNSET:
            field_dict["task_output_schema"] = task_output_schema
        if input_data_guide is not UNSET:
            field_dict["input_data_guide"] = input_data_guide
        if user_guidance is not UNSET:
            field_dict["user_guidance"] = user_guidance

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        task_prompt = d.pop("task_prompt")

        count = d.pop("count")

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

        def _parse_input_data_guide(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        input_data_guide = _parse_input_data_guide(d.pop("input_data_guide", UNSET))

        user_guidance = d.pop("user_guidance", UNSET)

        batch_plan_input = cls(
            task_prompt=task_prompt,
            count=count,
            task_input_schema=task_input_schema,
            task_output_schema=task_output_schema,
            input_data_guide=input_data_guide,
            user_guidance=user_guidance,
        )

        batch_plan_input.additional_properties = d
        return batch_plan_input

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
