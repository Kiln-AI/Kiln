from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.generate_batch_output_data_by_topic import GenerateBatchOutputDataByTopic


T = TypeVar("T", bound="GenerateBatchOutput")


@_attrs_define
class GenerateBatchOutput:
    """Output from batch generation, organized by topic.

    Attributes:
        data_by_topic (GenerateBatchOutputDataByTopic):
    """

    data_by_topic: GenerateBatchOutputDataByTopic
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data_by_topic = self.data_by_topic.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data_by_topic": data_by_topic,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.generate_batch_output_data_by_topic import GenerateBatchOutputDataByTopic

        d = dict(src_dict)
        data_by_topic = GenerateBatchOutputDataByTopic.from_dict(d.pop("data_by_topic"))

        generate_batch_output = cls(
            data_by_topic=data_by_topic,
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
