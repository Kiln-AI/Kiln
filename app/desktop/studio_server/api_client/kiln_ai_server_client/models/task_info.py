from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TaskInfo")


@_attrs_define
class TaskInfo:
    """
    Attributes:
        task_prompt (str):
        few_shot_examples (None | str | Unset):
    """

    task_prompt: str
    few_shot_examples: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_prompt = self.task_prompt

        few_shot_examples: None | str | Unset
        if isinstance(self.few_shot_examples, Unset):
            few_shot_examples = UNSET
        else:
            few_shot_examples = self.few_shot_examples

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_prompt": task_prompt,
            }
        )
        if few_shot_examples is not UNSET:
            field_dict["few_shot_examples"] = few_shot_examples

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        task_prompt = d.pop("task_prompt")

        def _parse_few_shot_examples(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        few_shot_examples = _parse_few_shot_examples(d.pop("few_shot_examples", UNSET))

        task_info = cls(
            task_prompt=task_prompt,
            few_shot_examples=few_shot_examples,
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
