from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.generate_batch_output_data_by_topic import GenerateBatchOutputDataByTopic


T = TypeVar("T", bound="GenerateBatchOutput")


@_attrs_define
class GenerateBatchOutput:
    """Output from batch generation, organized by topic.

    Attributes:
        data_by_topic (GenerateBatchOutputDataByTopic):
        topic_gen_prompt (None | str | Unset):
        input_gen_prompt (None | str | Unset):
        judge_prompt (None | str | Unset):
    """

    data_by_topic: GenerateBatchOutputDataByTopic
    topic_gen_prompt: None | str | Unset = UNSET
    input_gen_prompt: None | str | Unset = UNSET
    judge_prompt: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data_by_topic = self.data_by_topic.to_dict()

        topic_gen_prompt: None | str | Unset
        if isinstance(self.topic_gen_prompt, Unset):
            topic_gen_prompt = UNSET
        else:
            topic_gen_prompt = self.topic_gen_prompt

        input_gen_prompt: None | str | Unset
        if isinstance(self.input_gen_prompt, Unset):
            input_gen_prompt = UNSET
        else:
            input_gen_prompt = self.input_gen_prompt

        judge_prompt: None | str | Unset
        if isinstance(self.judge_prompt, Unset):
            judge_prompt = UNSET
        else:
            judge_prompt = self.judge_prompt

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data_by_topic": data_by_topic,
            }
        )
        if topic_gen_prompt is not UNSET:
            field_dict["topic_gen_prompt"] = topic_gen_prompt
        if input_gen_prompt is not UNSET:
            field_dict["input_gen_prompt"] = input_gen_prompt
        if judge_prompt is not UNSET:
            field_dict["judge_prompt"] = judge_prompt

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.generate_batch_output_data_by_topic import GenerateBatchOutputDataByTopic

        d = dict(src_dict)
        data_by_topic = GenerateBatchOutputDataByTopic.from_dict(d.pop("data_by_topic"))

        def _parse_topic_gen_prompt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        topic_gen_prompt = _parse_topic_gen_prompt(d.pop("topic_gen_prompt", UNSET))

        def _parse_input_gen_prompt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        input_gen_prompt = _parse_input_gen_prompt(d.pop("input_gen_prompt", UNSET))

        def _parse_judge_prompt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        judge_prompt = _parse_judge_prompt(d.pop("judge_prompt", UNSET))

        generate_batch_output = cls(
            data_by_topic=data_by_topic,
            topic_gen_prompt=topic_gen_prompt,
            input_gen_prompt=input_gen_prompt,
            judge_prompt=judge_prompt,
        )

        generate_batch_output.additional_properties = d
        return generate_batch_output

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
