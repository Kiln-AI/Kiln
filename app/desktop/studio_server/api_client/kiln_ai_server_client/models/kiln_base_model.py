from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="KilnBaseModel")


@_attrs_define
class KilnBaseModel:
    """Base model for all Kiln data models with common functionality for persistence and versioning.

    Attributes:
        v (int): Schema version number for migration support
        id (str): Unique identifier for the model instance
        path (Path): File system path where the model is stored
        created_at (datetime): Timestamp when the model was created
        created_by (str): User ID of the creator

        Attributes:
            model_type (str):
            v (int | Unset): Schema version for migration support. Default: 1.
            id (None | str | Unset): Unique identifier for this record.
            path (None | str | Unset): File system path where the record is stored.
            created_at (datetime.datetime | Unset): Timestamp when the model was created.
            created_by (str | Unset): User ID of the creator.
    """

    model_type: str
    v: int | Unset = 1
    id: None | str | Unset = UNSET
    path: None | str | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    created_by: str | Unset = UNSET
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

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
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

        kiln_base_model = cls(
            model_type=model_type,
            v=v,
            id=id,
            path=path,
            created_at=created_at,
            created_by=created_by,
        )

        kiln_base_model.additional_properties = d
        return kiln_base_model

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
