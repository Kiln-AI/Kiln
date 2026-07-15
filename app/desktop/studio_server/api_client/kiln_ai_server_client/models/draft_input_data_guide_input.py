from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="DraftInputDataGuideInput")


@_attrs_define
class DraftInputDataGuideInput:
    """Request payload for the draft step of the Input Data Guide copilot.

    Attributes:
        task_prompt (str): The task's runtime system prompt — used to ground the analysis.
        input_examples (list[str]): List of structured input summaries — each is a markdown string with sections `## 1.
            Shape`, `## 2. Meaning`, `## 3. Representative Excerpt`, produced by the upstream summarize stage. One summary
            per reference input.
        task_input_schema (None | str | Unset): If the task's input must conform to a JSON schema, provided here.
    """

    task_prompt: str
    input_examples: list[str]
    task_input_schema: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_prompt = self.task_prompt

        input_examples = self.input_examples

        task_input_schema: None | str | Unset
        if isinstance(self.task_input_schema, Unset):
            task_input_schema = UNSET
        else:
            task_input_schema = self.task_input_schema

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_prompt": task_prompt,
                "input_examples": input_examples,
            }
        )
        if task_input_schema is not UNSET:
            field_dict["task_input_schema"] = task_input_schema

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        task_prompt = d.pop("task_prompt")

        input_examples = cast(list[str], d.pop("input_examples"))

        def _parse_task_input_schema(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        task_input_schema = _parse_task_input_schema(d.pop("task_input_schema", UNSET))

        draft_input_data_guide_input = cls(
            task_prompt=task_prompt,
            input_examples=input_examples,
            task_input_schema=task_input_schema,
        )

        draft_input_data_guide_input.additional_properties = d
        return draft_input_data_guide_input

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
