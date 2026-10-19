from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="GenerateSyntheticUsersRequest")


@_attrs_define
class GenerateSyntheticUsersRequest:
    """Request body for POST /v1/synthetic_user/generate.

    One case per entry in `case_scenarios`, each probing `target_specification`
    against the agent described by `target_task_prompt`.

        Attributes:
            target_task_prompt (str): Complete prompt of the target task (the AI assistant under evaluation). Used as
                material for designing realistic synthetic users; never executed by this endpoint.
            target_specification (str): Behavior or issue to investigate about the target task (e.g. 'hallucinates tax-year-
                specific rules for years before 2018'). Generated cases are designed so a multi-turn conversation will naturally
                surface this behavior.
            case_scenarios (list[str]): One brief per case; case i is designed around scenario i.
    """

    target_task_prompt: str
    target_specification: str
    case_scenarios: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        target_task_prompt = self.target_task_prompt

        target_specification = self.target_specification

        case_scenarios = self.case_scenarios

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "target_task_prompt": target_task_prompt,
                "target_specification": target_specification,
                "case_scenarios": case_scenarios,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        target_task_prompt = d.pop("target_task_prompt")

        target_specification = d.pop("target_specification")

        case_scenarios = cast(list[str], d.pop("case_scenarios"))

        generate_synthetic_users_request = cls(
            target_task_prompt=target_task_prompt,
            target_specification=target_specification,
            case_scenarios=case_scenarios,
        )

        generate_synthetic_users_request.additional_properties = d
        return generate_synthetic_users_request

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
