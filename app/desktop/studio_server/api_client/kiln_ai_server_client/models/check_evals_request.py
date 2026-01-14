from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.check_evals_request_eval_configs_item import CheckEvalsRequestEvalConfigsItem
    from ..models.check_evals_request_evals_item import CheckEvalsRequestEvalsItem


T = TypeVar("T", bound="CheckEvalsRequest")


@_attrs_define
class CheckEvalsRequest:
    """Request model for checking evals.

    Attributes:
        evals (list[CheckEvalsRequestEvalsItem]):
        eval_configs (list[CheckEvalsRequestEvalConfigsItem]):
    """

    evals: list[CheckEvalsRequestEvalsItem]
    eval_configs: list[CheckEvalsRequestEvalConfigsItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        evals = []
        for evals_item_data in self.evals:
            evals_item = evals_item_data.to_dict()
            evals.append(evals_item)

        eval_configs = []
        for eval_configs_item_data in self.eval_configs:
            eval_configs_item = eval_configs_item_data.to_dict()
            eval_configs.append(eval_configs_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "evals": evals,
                "eval_configs": eval_configs,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.check_evals_request_eval_configs_item import CheckEvalsRequestEvalConfigsItem
        from ..models.check_evals_request_evals_item import CheckEvalsRequestEvalsItem

        d = dict(src_dict)
        evals = []
        _evals = d.pop("evals")
        for evals_item_data in _evals:
            evals_item = CheckEvalsRequestEvalsItem.from_dict(evals_item_data)

            evals.append(evals_item)

        eval_configs = []
        _eval_configs = d.pop("eval_configs")
        for eval_configs_item_data in _eval_configs:
            eval_configs_item = CheckEvalsRequestEvalConfigsItem.from_dict(eval_configs_item_data)

            eval_configs.append(eval_configs_item)

        check_evals_request = cls(
            evals=evals,
            eval_configs=eval_configs,
        )

        check_evals_request.additional_properties = d
        return check_evals_request

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
