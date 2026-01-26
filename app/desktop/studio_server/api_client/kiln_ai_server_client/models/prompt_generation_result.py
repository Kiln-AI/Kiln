from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.task_metadata import TaskMetadata


T = TypeVar("T", bound="PromptGenerationResult")


@_attrs_define
class PromptGenerationResult:
    """Information about a prompt generation run.

    Attributes:
        task_metadata (TaskMetadata): Metadata about a task invocation.
        prompt (str):
    """

    task_metadata: TaskMetadata
    prompt: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_metadata = self.task_metadata.to_dict()

        prompt = self.prompt

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_metadata": task_metadata,
                "prompt": prompt,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_metadata import TaskMetadata

        d = dict(src_dict)
        task_metadata = TaskMetadata.from_dict(d.pop("task_metadata"))

        prompt = d.pop("prompt")

        prompt_generation_result = cls(
            task_metadata=task_metadata,
            prompt=prompt,
        )

        prompt_generation_result.additional_properties = d
        return prompt_generation_result

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
