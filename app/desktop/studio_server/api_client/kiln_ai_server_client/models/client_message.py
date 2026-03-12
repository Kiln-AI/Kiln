from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.client_message_part import ClientMessagePart
    from ..models.tool_invocation import ToolInvocation


T = TypeVar("T", bound="ClientMessage")


@_attrs_define
class ClientMessage:
    """
    Attributes:
        role (str):
        content (None | str | Unset):
        parts (list[ClientMessagePart] | None | Unset):
        tool_invocations (list[ToolInvocation] | None | Unset):
    """

    role: str
    content: None | str | Unset = UNSET
    parts: list[ClientMessagePart] | None | Unset = UNSET
    tool_invocations: list[ToolInvocation] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        role = self.role

        content: None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        else:
            content = self.content

        parts: list[dict[str, Any]] | None | Unset
        if isinstance(self.parts, Unset):
            parts = UNSET
        elif isinstance(self.parts, list):
            parts = []
            for parts_type_0_item_data in self.parts:
                parts_type_0_item = parts_type_0_item_data.to_dict()
                parts.append(parts_type_0_item)

        else:
            parts = self.parts

        tool_invocations: list[dict[str, Any]] | None | Unset
        if isinstance(self.tool_invocations, Unset):
            tool_invocations = UNSET
        elif isinstance(self.tool_invocations, list):
            tool_invocations = []
            for tool_invocations_type_0_item_data in self.tool_invocations:
                tool_invocations_type_0_item = tool_invocations_type_0_item_data.to_dict()
                tool_invocations.append(tool_invocations_type_0_item)

        else:
            tool_invocations = self.tool_invocations

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "role": role,
            }
        )
        if content is not UNSET:
            field_dict["content"] = content
        if parts is not UNSET:
            field_dict["parts"] = parts
        if tool_invocations is not UNSET:
            field_dict["toolInvocations"] = tool_invocations

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.client_message_part import ClientMessagePart
        from ..models.tool_invocation import ToolInvocation

        d = dict(src_dict)
        role = d.pop("role")

        def _parse_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        content = _parse_content(d.pop("content", UNSET))

        def _parse_parts(data: object) -> list[ClientMessagePart] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                parts_type_0 = []
                _parts_type_0 = data
                for parts_type_0_item_data in _parts_type_0:
                    parts_type_0_item = ClientMessagePart.from_dict(parts_type_0_item_data)

                    parts_type_0.append(parts_type_0_item)

                return parts_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ClientMessagePart] | None | Unset, data)

        parts = _parse_parts(d.pop("parts", UNSET))

        def _parse_tool_invocations(data: object) -> list[ToolInvocation] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tool_invocations_type_0 = []
                _tool_invocations_type_0 = data
                for tool_invocations_type_0_item_data in _tool_invocations_type_0:
                    tool_invocations_type_0_item = ToolInvocation.from_dict(tool_invocations_type_0_item_data)

                    tool_invocations_type_0.append(tool_invocations_type_0_item)

                return tool_invocations_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[ToolInvocation] | None | Unset, data)

        tool_invocations = _parse_tool_invocations(d.pop("toolInvocations", UNSET))

        client_message = cls(
            role=role,
            content=content,
            parts=parts,
            tool_invocations=tool_invocations,
        )

        client_message.additional_properties = d
        return client_message

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
