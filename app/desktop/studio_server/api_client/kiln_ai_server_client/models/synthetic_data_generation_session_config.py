from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.synthetic_data_generation_step_config import SyntheticDataGenerationStepConfig


T = TypeVar("T", bound="SyntheticDataGenerationSessionConfig")


@_attrs_define
class SyntheticDataGenerationSessionConfig:
    """Configuration for a synthetic data generation session

    Attributes:
        topic_generation_config (SyntheticDataGenerationStepConfig): Configuration for a synthetic data generation step.
        input_generation_config (SyntheticDataGenerationStepConfig): Configuration for a synthetic data generation step.
        output_generation_config (SyntheticDataGenerationStepConfig): Configuration for a synthetic data generation
            step.
    """

    topic_generation_config: SyntheticDataGenerationStepConfig
    input_generation_config: SyntheticDataGenerationStepConfig
    output_generation_config: SyntheticDataGenerationStepConfig
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
        from ..models.synthetic_data_generation_step_config import SyntheticDataGenerationStepConfig

        d = dict(src_dict)
        topic_generation_config = SyntheticDataGenerationStepConfig.from_dict(d.pop("topic_generation_config"))

        input_generation_config = SyntheticDataGenerationStepConfig.from_dict(d.pop("input_generation_config"))

        output_generation_config = SyntheticDataGenerationStepConfig.from_dict(d.pop("output_generation_config"))

        synthetic_data_generation_session_config = cls(
            topic_generation_config=topic_generation_config,
            input_generation_config=input_generation_config,
            output_generation_config=output_generation_config,
        )

        synthetic_data_generation_session_config.additional_properties = d
        return synthetic_data_generation_session_config

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
