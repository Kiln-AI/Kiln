from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="ChatSessionListItem")


@_attrs_define
class ChatSessionListItem:
    """Session list row — metadata only, no trace.

    Kept deliberately minimal so ``GET /chat/sessions`` never returns the full
    conversation history per row. Clients fetch a specific trace via
    ``GET /chat/sessions/{id}`` when they need it.

        Attributes:
            id (str):
            updated_at (datetime.datetime):
            title (str):
    """

    id: str
    updated_at: datetime.datetime
    title: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        updated_at = self.updated_at.isoformat()

        title = self.title

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "updated_at": updated_at,
                "title": title,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id")

        updated_at = isoparse(d.pop("updated_at"))

        title = d.pop("title")

        chat_session_list_item = cls(
            id=id,
            updated_at=updated_at,
            title=title,
        )

        chat_session_list_item.additional_properties = d
        return chat_session_list_item

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
