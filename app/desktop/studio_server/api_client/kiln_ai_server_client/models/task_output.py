from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.data_source import DataSource
    from ..models.task_output_rating import TaskOutputRating


T = TypeVar("T", bound="TaskOutput")


@_attrs_define
class TaskOutput:
    """An output for a specific task run.

    Contains the actual output content, its source (human or synthetic),
    and optional rating information.

        Attributes:
            output (str): The output of the task. JSON formatted for structured output, plaintext for unstructured output.
            model_type (str):
            v (int | Unset): Schema version for migration support. Default: 1.
            id (None | str | Unset): Unique identifier for this record.
            path (None | str | Unset): File system path where the record is stored.
            created_at (datetime.datetime | Unset): Timestamp when the model was created.
            created_by (str | Unset): User ID of the creator.
            source (DataSource | None | Unset): The source of the output: human or synthetic.
            rating (None | TaskOutputRating | Unset): The rating of the output
    """

    output: str
    model_type: str
    v: int | Unset = 1
    id: None | str | Unset = UNSET
    path: None | str | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    created_by: str | Unset = UNSET
    source: DataSource | None | Unset = UNSET
    rating: None | TaskOutputRating | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.data_source import DataSource
        from ..models.task_output_rating import TaskOutputRating

        output = self.output

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

        source: dict[str, Any] | None | Unset
        if isinstance(self.source, Unset):
            source = UNSET
        elif isinstance(self.source, DataSource):
            source = self.source.to_dict()
        else:
            source = self.source

        rating: dict[str, Any] | None | Unset
        if isinstance(self.rating, Unset):
            rating = UNSET
        elif isinstance(self.rating, TaskOutputRating):
            rating = self.rating.to_dict()
        else:
            rating = self.rating

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "output": output,
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
        if source is not UNSET:
            field_dict["source"] = source
        if rating is not UNSET:
            field_dict["rating"] = rating

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.data_source import DataSource
        from ..models.task_output_rating import TaskOutputRating

        d = dict(src_dict)
        output = d.pop("output")

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

        def _parse_source(data: object) -> DataSource | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                source_type_0 = DataSource.from_dict(data)

                return source_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DataSource | None | Unset, data)

        source = _parse_source(d.pop("source", UNSET))

        def _parse_rating(data: object) -> None | TaskOutputRating | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                rating_type_0 = TaskOutputRating.from_dict(data)

                return rating_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TaskOutputRating | Unset, data)

        rating = _parse_rating(d.pop("rating", UNSET))

        task_output = cls(
            output=output,
            model_type=model_type,
            v=v,
            id=id,
            path=path,
            created_at=created_at,
            created_by=created_by,
            source=source,
            rating=rating,
        )

        task_output.additional_properties = d
        return task_output

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
