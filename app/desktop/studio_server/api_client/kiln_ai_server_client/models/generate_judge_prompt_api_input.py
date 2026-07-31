from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.generate_judge_prompt_api_input_trace_type import GenerateJudgePromptApiInputTraceType

T = TypeVar("T", bound="GenerateJudgePromptApiInput")


@_attrs_define
class GenerateJudgePromptApiInput:
    """Request payload for the judge prompt authoring copilot.

    Attributes:
        target_specification (str): The specification describing what behavior the Target Task should exhibit or avoid
        target_task_prompt (str): Complete prompt for the Target Task including system instructions and few-shot
            examples
        trace_type (GenerateJudgePromptApiInputTraceType): Shape of the traces the judge will grade. Selects the
            authoring prompt: multi-turn rubrics reason over turn-labelled transcripts and tool activity, single-turn
            rubrics grade one input/output pair.
    """

    target_specification: str
    target_task_prompt: str
    trace_type: GenerateJudgePromptApiInputTraceType
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        target_specification = self.target_specification

        target_task_prompt = self.target_task_prompt

        trace_type = self.trace_type.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "target_specification": target_specification,
                "target_task_prompt": target_task_prompt,
                "trace_type": trace_type,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        target_specification = d.pop("target_specification")

        target_task_prompt = d.pop("target_task_prompt")

        trace_type = GenerateJudgePromptApiInputTraceType(d.pop("trace_type"))

        generate_judge_prompt_api_input = cls(
            target_specification=target_specification,
            target_task_prompt=target_task_prompt,
            trace_type=trace_type,
        )

        generate_judge_prompt_api_input.additional_properties = d
        return generate_judge_prompt_api_input

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
