from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.synthetic_user_case import SyntheticUserCase


T = TypeVar("T", bound="GenerateSyntheticUsersResponse")


@_attrs_define
class GenerateSyntheticUsersResponse:
    """Response body for POST /v1/synthetic_user/generate.

    `cases` is the strict-N batch contract: exactly `num_cases` cases on
    success. If any single generated case is malformed (e.g. an empty
    `synthetic_user_info` blob), the whole batch fails with HTTP 502
    `upstream_invalid_output` — the server does not return a partial batch.
    Clients should re-call to retry.

        Attributes:
            cases (list[SyntheticUserCase]):
    """

    cases: list[SyntheticUserCase]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cases = []
        for cases_item_data in self.cases:
            cases_item = cases_item_data.to_dict()
            cases.append(cases_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cases": cases,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.synthetic_user_case import SyntheticUserCase

        d = dict(src_dict)
        cases = []
        _cases = d.pop("cases")
        for cases_item_data in _cases:
            cases_item = SyntheticUserCase.from_dict(cases_item_data)

            cases.append(cases_item)

        generate_synthetic_users_response = cls(
            cases=cases,
        )

        generate_synthetic_users_response.additional_properties = d
        return generate_synthetic_users_response

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
