from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SyntheticUserCase")


@_attrs_define
class SyntheticUserCase:
    """One generated synthetic-user case used to seed a probing conversation.

    Attributes:
        seed_prompt (str): Synthetic user's first message, written in their own voice.
        synthetic_user_info (str): XML-tagged blob describing the synthetic user, in the format
            `<persona>...</persona><goal>...</goal><behavior_guidance>...</behavior_guidance>`. Parse client-side. Tag names
            are stable; future versions may add new optional tags, but existing tags will not be renamed or removed.
    """

    seed_prompt: str
    synthetic_user_info: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        seed_prompt = self.seed_prompt

        synthetic_user_info = self.synthetic_user_info

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "seed_prompt": seed_prompt,
                "synthetic_user_info": synthetic_user_info,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        seed_prompt = d.pop("seed_prompt")

        synthetic_user_info = d.pop("synthetic_user_info")

        synthetic_user_case = cls(
            seed_prompt=seed_prompt,
            synthetic_user_info=synthetic_user_info,
        )

        synthetic_user_case.additional_properties = d
        return synthetic_user_case

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
