from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="TaskInfo")


@_attrs_define
class TaskInfo:
    """
    Attributes:
        task_prompt (str): The Target Task prompt
        few_shot_examples (None | str | Unset): Optional few-shot examples if used in task_prompt
    """

    task_prompt: str
    few_shot_examples: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        task_prompt = self.task_prompt

        few_shot_examples: None | str | Unset
        if isinstance(self.few_shot_examples, Unset):
            few_shot_examples = UNSET
        else:
            few_shot_examples = self.few_shot_examples

        field_dict: dict[str, Any] = {}

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

        return task_info
