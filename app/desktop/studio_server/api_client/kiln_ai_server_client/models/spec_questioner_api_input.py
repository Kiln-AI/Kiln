from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.task_info import TaskInfo


T = TypeVar("T", bound="SpecQuestionerApiInput")


@_attrs_define
class SpecQuestionerApiInput:
    """
    Attributes:
        target_task_info (TaskInfo): Shared information about a task
        target_specification (str):
    """

    target_task_info: TaskInfo
    target_specification: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        target_task_info = self.target_task_info.to_dict()

        target_specification = self.target_specification

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "target_task_info": target_task_info,
                "target_specification": target_specification,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_info import TaskInfo

        d = dict(src_dict)
        target_task_info = TaskInfo.from_dict(d.pop("target_task_info"))

        target_specification = d.pop("target_specification")

        spec_questioner_api_input = cls(
            target_task_info=target_task_info,
            target_specification=target_specification,
        )

        spec_questioner_api_input.additional_properties = d
        return spec_questioner_api_input

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
