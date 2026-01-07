from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ClarifySpecInput")


@_attrs_define
class ClarifySpecInput:
    """
    Attributes:
        task_prompt_with_few_shot (str):
        task_input_schema (str):
        task_output_schema (str):
        spec_rendered_prompt_template (str):
        num_samples_per_topic (int):
        num_topics (int):
        num_exemplars (int | Unset):  Default: 10.
    """

    task_prompt_with_few_shot: str
    task_input_schema: str
    task_output_schema: str
    spec_rendered_prompt_template: str
    num_samples_per_topic: int
    num_topics: int
    num_exemplars: int | Unset = 10
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_prompt_with_few_shot = self.task_prompt_with_few_shot

        task_input_schema = self.task_input_schema

        task_output_schema = self.task_output_schema

        spec_rendered_prompt_template = self.spec_rendered_prompt_template

        num_samples_per_topic = self.num_samples_per_topic

        num_topics = self.num_topics

        num_exemplars = self.num_exemplars

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_prompt_with_few_shot": task_prompt_with_few_shot,
                "task_input_schema": task_input_schema,
                "task_output_schema": task_output_schema,
                "spec_rendered_prompt_template": spec_rendered_prompt_template,
                "num_samples_per_topic": num_samples_per_topic,
                "num_topics": num_topics,
            }
        )
        if num_exemplars is not UNSET:
            field_dict["num_exemplars"] = num_exemplars

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        task_prompt_with_few_shot = d.pop("task_prompt_with_few_shot")

        task_input_schema = d.pop("task_input_schema")

        task_output_schema = d.pop("task_output_schema")

        spec_rendered_prompt_template = d.pop("spec_rendered_prompt_template")

        num_samples_per_topic = d.pop("num_samples_per_topic")

        num_topics = d.pop("num_topics")

        num_exemplars = d.pop("num_exemplars", UNSET)

        clarify_spec_input = cls(
            task_prompt_with_few_shot=task_prompt_with_few_shot,
            task_input_schema=task_input_schema,
            task_output_schema=task_output_schema,
            spec_rendered_prompt_template=spec_rendered_prompt_template,
            num_samples_per_topic=num_samples_per_topic,
            num_topics=num_topics,
            num_exemplars=num_exemplars,
        )

        clarify_spec_input.additional_properties = d
        return clarify_spec_input

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
