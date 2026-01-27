from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.task_info import TaskInfo


T = TypeVar("T", bound="GenerateBatchInput")


@_attrs_define
class GenerateBatchInput:
    """Input for batch generation (topics, inputs, outputs, optionally with scoring).

    Attributes:
        target_task_info (TaskInfo): Shared information about a task
        topic_generation_task_info (TaskInfo): Shared information about a task
        input_generation_task_info (TaskInfo): Shared information about a task
        target_specification (str):
        num_samples_per_topic (int):
        num_topics (int):
    """

    target_task_info: TaskInfo
    topic_generation_task_info: TaskInfo
    input_generation_task_info: TaskInfo
    target_specification: str
    num_samples_per_topic: int
    num_topics: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        target_task_info = self.target_task_info.to_dict()

        topic_generation_task_info = self.topic_generation_task_info.to_dict()

        input_generation_task_info = self.input_generation_task_info.to_dict()

        target_specification = self.target_specification

        num_samples_per_topic = self.num_samples_per_topic

        num_topics = self.num_topics

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "target_task_info": target_task_info,
                "topic_generation_task_info": topic_generation_task_info,
                "input_generation_task_info": input_generation_task_info,
                "target_specification": target_specification,
                "num_samples_per_topic": num_samples_per_topic,
                "num_topics": num_topics,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_info import TaskInfo

        d = dict(src_dict)
        target_task_info = TaskInfo.from_dict(d.pop("target_task_info"))

        topic_generation_task_info = TaskInfo.from_dict(d.pop("topic_generation_task_info"))

        input_generation_task_info = TaskInfo.from_dict(d.pop("input_generation_task_info"))

        target_specification = d.pop("target_specification")

        num_samples_per_topic = d.pop("num_samples_per_topic")

        num_topics = d.pop("num_topics")

        generate_batch_input = cls(
            target_task_info=target_task_info,
            topic_generation_task_info=topic_generation_task_info,
            input_generation_task_info=input_generation_task_info,
            target_specification=target_specification,
            num_samples_per_topic=num_samples_per_topic,
            num_topics=num_topics,
        )

        generate_batch_input.additional_properties = d
        return generate_batch_input

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
