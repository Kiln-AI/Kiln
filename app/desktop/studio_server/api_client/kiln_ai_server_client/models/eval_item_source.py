from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.eval_item_source_source_type import EvalItemSourceSourceType

T = TypeVar("T", bound="EvalItemSource")


@_attrs_define
class EvalItemSource:
    """The eval dataset item a TaskRun was generated for.

    Not the run config — that lives on the same TaskRun at
    `output.source.run_config_id`.

        Attributes:
            source_type (EvalItemSourceSourceType): Which store the dataset item came from: an EvalInput (V2) or a TaskRun
                (V1-backed split).
            source_id (str): The id of the dataset item this run was generated for. Interpreted within the store named by
                source_type — ids are only unique within a store.
    """

    source_type: EvalItemSourceSourceType
    source_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source_type = self.source_type.value

        source_id = self.source_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "source_type": source_type,
                "source_id": source_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        source_type = EvalItemSourceSourceType(d.pop("source_type"))

        source_id = d.pop("source_id")

        eval_item_source = cls(
            source_type=source_type,
            source_id=source_id,
        )

        eval_item_source.additional_properties = d
        return eval_item_source

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
