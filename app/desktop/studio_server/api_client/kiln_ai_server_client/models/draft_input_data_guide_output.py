from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="DraftInputDataGuideOutput")


@_attrs_define
class DraftInputDataGuideOutput:
    """Response payload for the draft step of the Input Data Guide copilot.

    Attributes:
        draft_guide (str): Full draft input data guide markdown. Contains exactly three top-level sections in order: `#
            Semantics`, `# Style`, `# Presentation Defaults`.
    """

    draft_guide: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        draft_guide = self.draft_guide

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "draft_guide": draft_guide,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        draft_guide = d.pop("draft_guide")

        draft_input_data_guide_output = cls(
            draft_guide=draft_guide,
        )

        draft_input_data_guide_output.additional_properties = d
        return draft_input_data_guide_output

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
