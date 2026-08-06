from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="BatchPlanOutput")


@_attrs_define
class BatchPlanOutput:
    """Response payload for the batch planner copilot.

    Attributes:
        prompts (list[str]): One tailored generation prompt per input; length equals the requested count.
        summary (str): A short, user-facing overview of the planned batch.
    """

    prompts: list[str]
    summary: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        prompts = self.prompts

        summary = self.summary

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "prompts": prompts,
                "summary": summary,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        prompts = cast(list[str], d.pop("prompts"))

        summary = d.pop("summary")

        batch_plan_output = cls(
            prompts=prompts,
            summary=summary,
        )

        batch_plan_output.additional_properties = d
        return batch_plan_output

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
