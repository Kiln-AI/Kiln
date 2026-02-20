from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.new_proposed_spec_edit_api import NewProposedSpecEditApi


T = TypeVar("T", bound="RefineSpecApiOutput")


@_attrs_define
class RefineSpecApiOutput:
    """Output from refining a spec.

    Attributes:
        new_proposed_spec_edits (list[NewProposedSpecEditApi]):
        not_incorporated_feedback (None | str):
    """

    new_proposed_spec_edits: list[NewProposedSpecEditApi]
    not_incorporated_feedback: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        new_proposed_spec_edits = []
        for new_proposed_spec_edits_item_data in self.new_proposed_spec_edits:
            new_proposed_spec_edits_item = new_proposed_spec_edits_item_data.to_dict()
            new_proposed_spec_edits.append(new_proposed_spec_edits_item)

        not_incorporated_feedback: None | str
        not_incorporated_feedback = self.not_incorporated_feedback

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "new_proposed_spec_edits": new_proposed_spec_edits,
                "not_incorporated_feedback": not_incorporated_feedback,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.new_proposed_spec_edit_api import NewProposedSpecEditApi

        d = dict(src_dict)
        new_proposed_spec_edits = []
        _new_proposed_spec_edits = d.pop("new_proposed_spec_edits")
        for new_proposed_spec_edits_item_data in _new_proposed_spec_edits:
            new_proposed_spec_edits_item = NewProposedSpecEditApi.from_dict(new_proposed_spec_edits_item_data)

            new_proposed_spec_edits.append(new_proposed_spec_edits_item)

        def _parse_not_incorporated_feedback(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        not_incorporated_feedback = _parse_not_incorporated_feedback(d.pop("not_incorporated_feedback"))

        refine_spec_api_output = cls(
            new_proposed_spec_edits=new_proposed_spec_edits,
            not_incorporated_feedback=not_incorporated_feedback,
        )

        refine_spec_api_output.additional_properties = d
        return refine_spec_api_output

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
