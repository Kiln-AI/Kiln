from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.model_provider_name import ModelProviderName

T = TypeVar("T", bound="TaskMetadata")


@_attrs_define
class TaskMetadata:
    """Metadata about a task invocation.

    Attributes:
        model_name (str):
        model_provider_name (ModelProviderName): Enumeration of supported AI model providers.
    """

    model_name: str
    model_provider_name: ModelProviderName
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        model_name = self.model_name

        model_provider_name = self.model_provider_name.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "model_name": model_name,
                "model_provider_name": model_provider_name,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        model_name = d.pop("model_name")

        model_provider_name = ModelProviderName(d.pop("model_provider_name"))

        task_metadata = cls(
            model_name=model_name,
            model_provider_name=model_provider_name,
        )

        task_metadata.additional_properties = d
        return task_metadata

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
