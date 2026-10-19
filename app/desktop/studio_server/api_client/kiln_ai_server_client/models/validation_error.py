from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.validation_error_context import ValidationErrorContext


T = TypeVar("T", bound="ValidationError")


@_attrs_define
class ValidationError:
    """
    Attributes:
        loc (list[int | str]):
        msg (str):
        type_ (str):
        input_ (Any | Unset):
        ctx (ValidationErrorContext | Unset):
    """

    loc: list[int | str]
    msg: str
    type_: str
    input_: Any | Unset = UNSET
    ctx: ValidationErrorContext | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        loc = []
        for loc_item_data in self.loc:
            loc_item: int | str
            loc_item = loc_item_data
            loc.append(loc_item)

        msg = self.msg

        type_ = self.type_

        input_ = self.input_

        ctx: dict[str, Any] | Unset = UNSET
        if not isinstance(self.ctx, Unset):
            ctx = self.ctx.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "loc": loc,
                "msg": msg,
                "type": type_,
            }
        )
        if input_ is not UNSET:
            field_dict["input"] = input_
        if ctx is not UNSET:
            field_dict["ctx"] = ctx

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.validation_error_context import ValidationErrorContext

        d = dict(src_dict)
        loc = []
        _loc = d.pop("loc")
        for loc_item_data in _loc:

            def _parse_loc_item(data: object) -> int | str:
                return cast(int | str, data)

            loc_item = _parse_loc_item(loc_item_data)

            loc.append(loc_item)

        msg = d.pop("msg")

        type_ = d.pop("type")

        input_ = d.pop("input", UNSET)

        _ctx = d.pop("ctx", UNSET)
        ctx: ValidationErrorContext | Unset
        if isinstance(_ctx, Unset):
            ctx = UNSET
        else:
            ctx = ValidationErrorContext.from_dict(_ctx)

        validation_error = cls(
            loc=loc,
            msg=msg,
            type_=type_,
            input_=input_,
            ctx=ctx,
        )

        validation_error.additional_properties = d
        return validation_error

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
