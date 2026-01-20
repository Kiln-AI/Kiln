from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.model_provider_name import ModelProviderName

T = TypeVar("T", bound="JudgeInfo")


@_attrs_define
class JudgeInfo:
    """
    Attributes:
        model_id (str):
        model_provider (ModelProviderName): Enumeration of supported AI model providers.
        judge_prompt (str):
    """

    model_id: str
    model_provider: ModelProviderName
    judge_prompt: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        model_id = self.model_id

        model_provider = self.model_provider.value

        judge_prompt = self.judge_prompt

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "model_id": model_id,
                "model_provider": model_provider,
                "judge_prompt": judge_prompt,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        model_id = d.pop("model_id")

        model_provider = ModelProviderName(d.pop("model_provider"))

        judge_prompt = d.pop("judge_prompt")

        judge_info = cls(
            model_id=model_id,
            model_provider=model_provider,
            judge_prompt=judge_prompt,
        )

        judge_info.additional_properties = d
        return judge_info

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
