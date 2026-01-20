from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

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

    def to_dict(self) -> dict[str, Any]:
        model_id = self.model_id

        model_provider = self.model_provider.value

        judge_prompt = self.judge_prompt

        field_dict: dict[str, Any] = {}

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

        return judge_info

