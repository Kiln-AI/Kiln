from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.synthetic_data_generation_step_config_input import SyntheticDataGenerationStepConfigInput


T = TypeVar("T", bound="SyntheticDataGenerationSessionConfigInput")


@_attrs_define
class SyntheticDataGenerationSessionConfigInput:
    """Same as SyntheticDataGenerationSessionConfig, but new name for our SDK auto-compile tool.

    Attributes:
        topic_generation_config (SyntheticDataGenerationStepConfigInput): Same as SyntheticDataGenerationStepConfig, but
            new name for our SDK auto-compile tool.
        input_generation_config (SyntheticDataGenerationStepConfigInput): Same as SyntheticDataGenerationStepConfig, but
            new name for our SDK auto-compile tool.
        output_generation_config (SyntheticDataGenerationStepConfigInput): Same as SyntheticDataGenerationStepConfig,
            but new name for our SDK auto-compile tool.
    """

    topic_generation_config: SyntheticDataGenerationStepConfigInput
    input_generation_config: SyntheticDataGenerationStepConfigInput
    output_generation_config: SyntheticDataGenerationStepConfigInput
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        topic_generation_config = self.topic_generation_config.to_dict()

        input_generation_config = self.input_generation_config.to_dict()

        output_generation_config = self.output_generation_config.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "topic_generation_config": topic_generation_config,
                "input_generation_config": input_generation_config,
                "output_generation_config": output_generation_config,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.synthetic_data_generation_step_config_input import SyntheticDataGenerationStepConfigInput

        d = dict(src_dict)
        topic_generation_config = SyntheticDataGenerationStepConfigInput.from_dict(d.pop("topic_generation_config"))

        input_generation_config = SyntheticDataGenerationStepConfigInput.from_dict(d.pop("input_generation_config"))

        output_generation_config = SyntheticDataGenerationStepConfigInput.from_dict(d.pop("output_generation_config"))

        synthetic_data_generation_session_config_input = cls(
            topic_generation_config=topic_generation_config,
            input_generation_config=input_generation_config,
            output_generation_config=output_generation_config,
        )

        synthetic_data_generation_session_config_input.additional_properties = d
        return synthetic_data_generation_session_config_input

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
