from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.requirement_rating import RequirementRating


T = TypeVar("T", bound="TaskOutputRatingRequirementRatings")


@_attrs_define
class TaskOutputRatingRequirementRatings:
    """The ratings of the requirements of the task. The ID can be either a task_requirement_id or a named rating for an
    eval_output_score name (in format 'named::<name>').

    """

    additional_properties: dict[str, RequirementRating] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.to_dict()

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.requirement_rating import RequirementRating

        d = dict(src_dict)
        task_output_rating_requirement_ratings = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = RequirementRating.from_dict(prop_dict)

            additional_properties[prop_name] = additional_property

        task_output_rating_requirement_ratings.additional_properties = additional_properties
        return task_output_rating_requirement_ratings

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> RequirementRating:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: RequirementRating) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
