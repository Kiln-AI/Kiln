from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.model_provider_name import ModelProviderName
from ..models.structured_output_mode import StructuredOutputMode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tools_run_config import ToolsRunConfig


T = TypeVar("T", bound="KilnAgentRunConfigProperties")


@_attrs_define
class KilnAgentRunConfigProperties:
    """A configuration for running a task using a Kiln AI agent.

    This includes everything needed to run a task, except the input and task ID. Running the same RunConfig with the
    same input should make identical calls to the model (output may vary as models are non-deterministic).

        Attributes:
            model_name (str): The model to use for this run config.
            model_provider_name (ModelProviderName): Enumeration of supported AI model providers.
            prompt_id (str): The prompt to use for this run config. Defaults to building a simple prompt from the task if
                not provided.
            structured_output_mode (StructuredOutputMode): Enumeration of supported structured output modes.

                - json_schema: request json using API capabilities for json_schema
                - function_calling: request json using API capabilities for function calling
                - json_mode: request json using API's JSON mode, which should return valid JSON, but isn't checking/passing the
                schema
                - json_instructions: append instructions to the prompt to request json matching the schema. No API capabilities
                are used. You should have a custom parser on these models as they will be returning strings.
                - json_instruction_and_object: append instructions to the prompt to request json matching the schema. Also
                request the response as json_mode via API capabilities (returning dictionaries).
                - json_custom_instructions: The model should output JSON, but custom instructions are already included in the
                system prompt. Don't append additional JSON instructions.
                - default: let the adapter decide (legacy, do not use for new use cases)
                - unknown: used for cases where the structured output mode is not known (on old models where it wasn't saved).
                Should lookup best option at runtime.
            type_ (Literal['kiln_agent'] | Unset):  Default: 'kiln_agent'.
            top_p (float | Unset): The top-p value to use for this run config. Defaults to 1.0. Default: 1.0.
            temperature (float | Unset): The temperature to use for this run config. Defaults to 1.0. Default: 1.0.
            thinking_level (None | str | Unset): The thinking level to use for this run config. If None, defaults may apply.
            tools_config (None | ToolsRunConfig | Unset): The tools config to use for this run config, defining which tools
                are available to the model.
    """

    model_name: str
    model_provider_name: ModelProviderName
    prompt_id: str
    structured_output_mode: StructuredOutputMode
    type_: Literal["kiln_agent"] | Unset = "kiln_agent"
    top_p: float | Unset = 1.0
    temperature: float | Unset = 1.0
    thinking_level: None | str | Unset = UNSET
    tools_config: None | ToolsRunConfig | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.tools_run_config import ToolsRunConfig

        model_name = self.model_name

        model_provider_name = self.model_provider_name.value

        prompt_id = self.prompt_id

        structured_output_mode = self.structured_output_mode.value

        type_ = self.type_

        top_p = self.top_p

        temperature = self.temperature

        thinking_level: None | str | Unset
        if isinstance(self.thinking_level, Unset):
            thinking_level = UNSET
        else:
            thinking_level = self.thinking_level

        tools_config: dict[str, Any] | None | Unset
        if isinstance(self.tools_config, Unset):
            tools_config = UNSET
        elif isinstance(self.tools_config, ToolsRunConfig):
            tools_config = self.tools_config.to_dict()
        else:
            tools_config = self.tools_config

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "model_name": model_name,
                "model_provider_name": model_provider_name,
                "prompt_id": prompt_id,
                "structured_output_mode": structured_output_mode,
            }
        )
        if type_ is not UNSET:
            field_dict["type"] = type_
        if top_p is not UNSET:
            field_dict["top_p"] = top_p
        if temperature is not UNSET:
            field_dict["temperature"] = temperature
        if thinking_level is not UNSET:
            field_dict["thinking_level"] = thinking_level
        if tools_config is not UNSET:
            field_dict["tools_config"] = tools_config

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tools_run_config import ToolsRunConfig

        d = dict(src_dict)
        model_name = d.pop("model_name")

        model_provider_name = ModelProviderName(d.pop("model_provider_name"))

        prompt_id = d.pop("prompt_id")

        structured_output_mode = StructuredOutputMode(d.pop("structured_output_mode"))

        type_ = cast(Literal["kiln_agent"] | Unset, d.pop("type", UNSET))
        if type_ != "kiln_agent" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'kiln_agent', got '{type_}'")

        top_p = d.pop("top_p", UNSET)

        temperature = d.pop("temperature", UNSET)

        def _parse_thinking_level(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        thinking_level = _parse_thinking_level(d.pop("thinking_level", UNSET))

        def _parse_tools_config(data: object) -> None | ToolsRunConfig | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                tools_config_type_0 = ToolsRunConfig.from_dict(data)

                return tools_config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ToolsRunConfig | Unset, data)

        tools_config = _parse_tools_config(d.pop("tools_config", UNSET))

        kiln_agent_run_config_properties = cls(
            model_name=model_name,
            model_provider_name=model_provider_name,
            prompt_id=prompt_id,
            structured_output_mode=structured_output_mode,
            type_=type_,
            top_p=top_p,
            temperature=temperature,
            thinking_level=thinking_level,
            tools_config=tools_config,
        )

        kiln_agent_run_config_properties.additional_properties = d
        return kiln_agent_run_config_properties

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
