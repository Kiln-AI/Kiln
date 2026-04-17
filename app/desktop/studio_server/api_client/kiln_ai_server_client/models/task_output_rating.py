from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.task_output_rating_type import TaskOutputRatingType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.task_output_rating_requirement_ratings import TaskOutputRatingRequirementRatings


T = TypeVar("T", bound="TaskOutputRating")


@_attrs_define
class TaskOutputRating:
    """A rating for a task output, including an overall rating and ratings for each requirement.

    Supports:
    - five_star: 1-5 star ratings
    - pass_fail: boolean pass/fail (1.0 = pass, 0.0 = fail)
    - pass_fail_critical: tri-state (1.0 = pass, 0.0 = fail, -1.0 = critical fail)

        Attributes:
            model_type (str):
            v (int | Unset): Schema version for migration support. Default: 1.
            id (None | str | Unset): Unique identifier for this record.
            path (None | str | Unset): File system path where the record is stored.
            created_at (datetime.datetime | Unset): Timestamp when the model was created.
            created_by (str | Unset): User ID of the creator.
            type_ (TaskOutputRatingType | Unset): Defines the types of rating systems available for task outputs.
            value (float | None | Unset): The rating value. Interpretation depends on rating type:
                - five_star: 1-5 stars
                - pass_fail: 1.0 (pass) or 0.0 (fail)
                - pass_fail_critical: 1.0 (pass), 0.0 (fail), or -1.0 (critical fail)
            requirement_ratings (TaskOutputRatingRequirementRatings | Unset): The ratings of the requirements of the task.
                The ID can be either a task_requirement_id or a named rating for an eval_output_score name (in format
                'named::<name>').
    """

    model_type: str
    v: int | Unset = 1
    id: None | str | Unset = UNSET
    path: None | str | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    created_by: str | Unset = UNSET
    type_: TaskOutputRatingType | Unset = UNSET
    value: float | None | Unset = UNSET
    requirement_ratings: TaskOutputRatingRequirementRatings | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        model_type = self.model_type

        v = self.v

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        path: None | str | Unset
        if isinstance(self.path, Unset):
            path = UNSET
        else:
            path = self.path

        created_at: str | Unset = UNSET
        if not isinstance(self.created_at, Unset):
            created_at = self.created_at.isoformat()

        created_by = self.created_by

        type_: str | Unset = UNSET
        if not isinstance(self.type_, Unset):
            type_ = self.type_.value

        value: float | None | Unset
        if isinstance(self.value, Unset):
            value = UNSET
        else:
            value = self.value

        requirement_ratings: dict[str, Any] | Unset = UNSET
        if not isinstance(self.requirement_ratings, Unset):
            requirement_ratings = self.requirement_ratings.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "model_type": model_type,
            }
        )
        if v is not UNSET:
            field_dict["v"] = v
        if id is not UNSET:
            field_dict["id"] = id
        if path is not UNSET:
            field_dict["path"] = path
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if created_by is not UNSET:
            field_dict["created_by"] = created_by
        if type_ is not UNSET:
            field_dict["type"] = type_
        if value is not UNSET:
            field_dict["value"] = value
        if requirement_ratings is not UNSET:
            field_dict["requirement_ratings"] = requirement_ratings

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_output_rating_requirement_ratings import TaskOutputRatingRequirementRatings

        d = dict(src_dict)
        model_type = d.pop("model_type")

        v = d.pop("v", UNSET)

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        path = _parse_path(d.pop("path", UNSET))

        _created_at = d.pop("created_at", UNSET)
        created_at: datetime.datetime | Unset
        if isinstance(_created_at, Unset):
            created_at = UNSET
        else:
            created_at = isoparse(_created_at)

        created_by = d.pop("created_by", UNSET)

        _type_ = d.pop("type", UNSET)
        type_: TaskOutputRatingType | Unset
        if isinstance(_type_, Unset):
            type_ = UNSET
        else:
            type_ = TaskOutputRatingType(_type_)

        def _parse_value(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        value = _parse_value(d.pop("value", UNSET))

        _requirement_ratings = d.pop("requirement_ratings", UNSET)
        requirement_ratings: TaskOutputRatingRequirementRatings | Unset
        if isinstance(_requirement_ratings, Unset):
            requirement_ratings = UNSET
        else:
            requirement_ratings = TaskOutputRatingRequirementRatings.from_dict(_requirement_ratings)

        task_output_rating = cls(
            model_type=model_type,
            v=v,
            id=id,
            path=path,
            created_at=created_at,
            created_by=created_by,
            type_=type_,
            value=value,
            requirement_ratings=requirement_ratings,
        )

        task_output_rating.additional_properties = d
        return task_output_rating

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
