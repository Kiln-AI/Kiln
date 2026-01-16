from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="NewProposedSpecEdits")


@_attrs_define
class NewProposedSpecEdits:
    """
    Attributes:
        old_value (str):
        proposed_edit (str):
        reason_for_edit (str):
    """

    old_value: str
    proposed_edit: str
    reason_for_edit: str

    def to_dict(self) -> dict[str, Any]:
        old_value = self.old_value

        proposed_edit = self.proposed_edit

        reason_for_edit = self.reason_for_edit

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "old_value": old_value,
                "proposed_edit": proposed_edit,
                "reason_for_edit": reason_for_edit,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        old_value = d.pop("old_value")

        proposed_edit = d.pop("proposed_edit")

        reason_for_edit = d.pop("reason_for_edit")

        new_proposed_spec_edits = cls(
            old_value=old_value,
            proposed_edit=proposed_edit,
            reason_for_edit=reason_for_edit,
        )

        return new_proposed_spec_edits
