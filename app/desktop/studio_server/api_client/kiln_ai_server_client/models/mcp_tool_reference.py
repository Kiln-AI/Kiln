from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.mcp_tool_reference_input_schema_type_0 import MCPToolReferenceInputSchemaType0
    from ..models.mcp_tool_reference_output_schema_type_0 import MCPToolReferenceOutputSchemaType0


T = TypeVar("T", bound="MCPToolReference")


@_attrs_define
class MCPToolReference:
    """
    Attributes:
        tool_id (str): The MCP tool ID to call (mcp::local|remote::<server_id>::<tool_name>).
        tool_server_id (None | str | Unset): The MCP tool server ID.
        tool_name (None | str | Unset): The MCP tool name.
        input_schema (MCPToolReferenceInputSchemaType0 | None | Unset): Snapshot of the MCP tool input schema.
        output_schema (MCPToolReferenceOutputSchemaType0 | None | Unset): Snapshot of the MCP tool output schema.
    """

    tool_id: str
    tool_server_id: None | str | Unset = UNSET
    tool_name: None | str | Unset = UNSET
    input_schema: MCPToolReferenceInputSchemaType0 | None | Unset = UNSET
    output_schema: MCPToolReferenceOutputSchemaType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.mcp_tool_reference_input_schema_type_0 import MCPToolReferenceInputSchemaType0
        from ..models.mcp_tool_reference_output_schema_type_0 import MCPToolReferenceOutputSchemaType0

        tool_id = self.tool_id

        tool_server_id: None | str | Unset
        if isinstance(self.tool_server_id, Unset):
            tool_server_id = UNSET
        else:
            tool_server_id = self.tool_server_id

        tool_name: None | str | Unset
        if isinstance(self.tool_name, Unset):
            tool_name = UNSET
        else:
            tool_name = self.tool_name

        input_schema: dict[str, Any] | None | Unset
        if isinstance(self.input_schema, Unset):
            input_schema = UNSET
        elif isinstance(self.input_schema, MCPToolReferenceInputSchemaType0):
            input_schema = self.input_schema.to_dict()
        else:
            input_schema = self.input_schema

        output_schema: dict[str, Any] | None | Unset
        if isinstance(self.output_schema, Unset):
            output_schema = UNSET
        elif isinstance(self.output_schema, MCPToolReferenceOutputSchemaType0):
            output_schema = self.output_schema.to_dict()
        else:
            output_schema = self.output_schema

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool_id": tool_id,
            }
        )
        if tool_server_id is not UNSET:
            field_dict["tool_server_id"] = tool_server_id
        if tool_name is not UNSET:
            field_dict["tool_name"] = tool_name
        if input_schema is not UNSET:
            field_dict["input_schema"] = input_schema
        if output_schema is not UNSET:
            field_dict["output_schema"] = output_schema

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mcp_tool_reference_input_schema_type_0 import MCPToolReferenceInputSchemaType0
        from ..models.mcp_tool_reference_output_schema_type_0 import MCPToolReferenceOutputSchemaType0

        d = dict(src_dict)
        tool_id = d.pop("tool_id")

        def _parse_tool_server_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tool_server_id = _parse_tool_server_id(d.pop("tool_server_id", UNSET))

        def _parse_tool_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tool_name = _parse_tool_name(d.pop("tool_name", UNSET))

        def _parse_input_schema(data: object) -> MCPToolReferenceInputSchemaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_schema_type_0 = MCPToolReferenceInputSchemaType0.from_dict(data)

                return input_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MCPToolReferenceInputSchemaType0 | None | Unset, data)

        input_schema = _parse_input_schema(d.pop("input_schema", UNSET))

        def _parse_output_schema(data: object) -> MCPToolReferenceOutputSchemaType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_schema_type_0 = MCPToolReferenceOutputSchemaType0.from_dict(data)

                return output_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MCPToolReferenceOutputSchemaType0 | None | Unset, data)

        output_schema = _parse_output_schema(d.pop("output_schema", UNSET))

        mcp_tool_reference = cls(
            tool_id=tool_id,
            tool_server_id=tool_server_id,
            tool_name=tool_name,
            input_schema=input_schema,
            output_schema=output_schema,
        )

        mcp_tool_reference.additional_properties = d
        return mcp_tool_reference

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
