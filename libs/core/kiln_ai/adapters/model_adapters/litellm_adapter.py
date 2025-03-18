from typing import Any, Dict

import litellm
from litellm.types.utils import ChoiceLogprobs, Choices, ModelResponse

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.ml_model_list import (
    KilnModelProvider,
    ModelProviderName,
    StructuredOutputMode,
)
from kiln_ai.adapters.model_adapters.base_adapter import (
    COT_FINAL_ANSWER_PROMPT,
    AdapterConfig,
    BaseAdapter,
    RunOutput,
)
from kiln_ai.adapters.model_adapters.litellm_config import (
    LiteLlmConfig,
)
from kiln_ai.datamodel import PromptGenerators, PromptId
from kiln_ai.datamodel.task import RunConfig
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


class LiteLlmAdapter(BaseAdapter):
    def __init__(
        self,
        config: LiteLlmConfig,
        kiln_task: datamodel.Task,
        prompt_id: PromptId | None = None,
        base_adapter_config: AdapterConfig | None = None,
    ):
        self.config = config
        self._additional_body_options = config.additional_body_options
        self._api_base = config.base_url
        self._headers = config.default_headers
        self._litellm_model_id: str | None = None

        run_config = RunConfig(
            task=kiln_task,
            model_name=config.model_name,
            model_provider_name=config.provider_name,
            prompt_id=prompt_id or PromptGenerators.SIMPLE,
        )

        super().__init__(
            run_config=run_config,
            config=base_adapter_config,
        )

    async def _run(self, input: Dict | str) -> RunOutput:
        provider = self.model_provider()
        if not provider.model_id:
            raise ValueError("Model ID is required for OpenAI compatible models")

        intermediate_outputs: dict[str, str] = {}
        prompt = self.build_prompt()
        user_msg = self.prompt_builder.build_user_message(input)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg},
        ]

        run_strategy, cot_prompt = self.run_strategy()

        if run_strategy == "cot_as_message":
            if not cot_prompt:
                raise ValueError("cot_prompt is required for cot_as_message strategy")
            messages.append({"role": "system", "content": cot_prompt})
        elif run_strategy == "cot_two_call":
            if not cot_prompt:
                raise ValueError("cot_prompt is required for cot_two_call strategy")
            messages.append({"role": "system", "content": cot_prompt})

            # First call for chain of thought - No logprobs as only needed for final answer
            completion_kwargs = await self.build_completion_kwargs(
                provider, messages, None
            )
            cot_response = await litellm.acompletion(**completion_kwargs)
            if (
                not isinstance(cot_response, ModelResponse)
                or not cot_response.choices
                or len(cot_response.choices) == 0
                or not isinstance(cot_response.choices[0], Choices)
            ):
                raise RuntimeError(
                    f"Expected ModelResponse with Choices, got {type(cot_response)}."
                )
            cot_content = cot_response.choices[0].message.content
            if cot_content is not None:
                intermediate_outputs["chain_of_thought"] = cot_content

            messages.extend(
                [
                    {"role": "assistant", "content": cot_content or ""},
                    {"role": "user", "content": COT_FINAL_ANSWER_PROMPT},
                ]
            )

        # Make the API call using litellm
        completion_kwargs = await self.build_completion_kwargs(
            provider, messages, self.base_adapter_config.top_logprobs
        )
        response = await litellm.acompletion(**completion_kwargs)

        if not isinstance(response, ModelResponse):
            raise RuntimeError(f"Expected ModelResponse, got {type(response)}.")

        # Maybe remove this? There is no error attribute on the response object.
        # # Keeping in typesafe way as we added it for a reason, but should investigate what that was and if it still applies.
        if hasattr(response, "error") and response.__getattribute__("error"):
            raise RuntimeError(
                f"LLM API returned an error: {response.__getattribute__('error')}"
            )

        if (
            not response.choices
            or len(response.choices) == 0
            or not isinstance(response.choices[0], Choices)
        ):
            raise RuntimeError(
                "No message content returned in the response from LLM API"
            )

        message = response.choices[0].message
        logprobs = (
            response.choices[0].logprobs
            if hasattr(response.choices[0], "logprobs")
            and isinstance(response.choices[0].logprobs, ChoiceLogprobs)
            else None
        )

        # Check logprobs worked, if requested
        if self.base_adapter_config.top_logprobs is not None and logprobs is None:
            raise RuntimeError("Logprobs were required, but no logprobs were returned.")

        # Save reasoning if it exists and was parsed by LiteLLM (or openrouter, or anyone upstream)
        if hasattr(message, "reasoning_content") and message.reasoning_content:
            intermediate_outputs["reasoning"] = message.reasoning_content

        # the string content of the response
        response_content = message.content

        # Fallback: Use args of first tool call to task_response if it exists
        if (
            not response_content
            and hasattr(message, "tool_calls")
            and message.tool_calls
        ):
            tool_call = next(
                (
                    tool_call
                    for tool_call in message.tool_calls
                    if tool_call.function.name == "task_response"
                ),
                None,
            )
            if tool_call:
                response_content = tool_call.function.arguments

        if not isinstance(response_content, str):
            raise RuntimeError(f"response is not a string: {response_content}")

        return RunOutput(
            output=response_content,
            intermediate_outputs=intermediate_outputs,
            output_logprobs=logprobs,
        )

    def adapter_name(self) -> str:
        return "kiln_openai_compatible_adapter"

    async def response_format_options(self) -> dict[str, Any]:
        # Unstructured if task isn't structured
        if not self.has_structured_output():
            return {}

        provider = self.model_provider()
        match provider.structured_output_mode:
            case StructuredOutputMode.json_mode:
                return {"response_format": {"type": "json_object"}}
            case StructuredOutputMode.json_schema:
                return self.json_schema_response_format()
            case StructuredOutputMode.function_calling_weak:
                return self.tool_call_params(strict=False)
            case StructuredOutputMode.function_calling:
                return self.tool_call_params(strict=True)
            case StructuredOutputMode.json_instructions:
                # JSON instructions dynamically injected in prompt, not the API response format. Do not ask for json_object (see option below).
                return {}
            case StructuredOutputMode.json_custom_instructions:
                # JSON instructions statically injected in system prompt, not the API response format. Do not ask for json_object (see option above).
                return {}
            case StructuredOutputMode.json_instruction_and_object:
                # We set response_format to json_object and also set json instructions in the prompt
                return {"response_format": {"type": "json_object"}}
            case StructuredOutputMode.default:
                if provider.name == ModelProviderName.ollama:
                    # Ollama added json_schema to all models: https://ollama.com/blog/structured-outputs
                    return self.json_schema_response_format()
                else:
                    # Default to function calling -- it's older than the other modes. Higher compatibility.
                    # Strict isn't widely supported yet, so we don't use it by default unless it's OpenAI.
                    strict = provider.name == ModelProviderName.openai
                    return self.tool_call_params(strict=strict)
            case _:
                raise_exhaustive_enum_error(provider.structured_output_mode)

    def json_schema_response_format(self) -> dict[str, Any]:
        output_schema = self.task().output_schema()
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "task_response",
                    "schema": output_schema,
                },
            }
        }

    def tool_call_params(self, strict: bool) -> dict[str, Any]:
        # Add additional_properties: false to the schema (OpenAI requires this for some models)
        output_schema = self.task().output_schema()
        if not isinstance(output_schema, dict):
            raise ValueError(
                "Invalid output schema for this task. Can not use tool calls."
            )
        output_schema["additionalProperties"] = False

        function_params = {
            "name": "task_response",
            "parameters": output_schema,
        }
        # This should be on, but we allow setting function_calling_weak for APIs that don't support it.
        if strict:
            function_params["strict"] = True

        return {
            "tools": [
                {
                    "type": "function",
                    "function": function_params,
                }
            ],
            "tool_choice": {
                "type": "function",
                "function": {"name": "task_response"},
            },
        }

    def build_extra_body(self, provider: KilnModelProvider) -> dict[str, Any]:
        # TODO P1: Don't love having this logic here. But it's a usability improvement
        # so better to keep it than exclude it. Should figure out how I want to isolate
        # this sort of logic so it's config driven and can be overridden

        extra_body = {}
        provider_options = {}

        if provider.thinking_level is not None:
            extra_body["reasoning_effort"] = provider.thinking_level

        if provider.require_openrouter_reasoning:
            # https://openrouter.ai/docs/use-cases/reasoning-tokens
            extra_body["reasoning"] = {
                "exclude": False,
            }

        if provider.anthropic_extended_thinking:
            extra_body["thinking"] = {"type": "enabled", "budget_tokens": 4000}

        if provider.r1_openrouter_options:
            # Require providers that support the reasoning parameter
            provider_options["require_parameters"] = True
            # Prefer R1 providers with reasonable perf/quants
            provider_options["order"] = ["Fireworks", "Together"]
            # R1 providers with unreasonable quants
            provider_options["ignore"] = ["DeepInfra"]

        # Only set of this request is to get logprobs.
        if (
            provider.logprobs_openrouter_options
            and self.base_adapter_config.top_logprobs is not None
        ):
            # Don't let OpenRouter choose a provider that doesn't support logprobs.
            provider_options["require_parameters"] = True
            # DeepInfra silently fails to return logprobs consistently.
            provider_options["ignore"] = ["DeepInfra"]

        if provider.openrouter_skip_required_parameters:
            # Oddball case, R1 14/8/1.5B fail with this param, even though they support thinking params.
            provider_options["require_parameters"] = False

        if len(provider_options) > 0:
            extra_body["provider"] = provider_options

        return extra_body

    def litellm_model_id(self) -> str:
        # The model ID is an interesting combination of format and url endpoint.
        # It specifics the provider URL/host, but this is overridden if you manually set an api url

        if self._litellm_model_id:
            return self._litellm_model_id

        provider = self.model_provider()
        if not provider.model_id:
            raise ValueError("Model ID is required for OpenAI compatible models")

        litellm_provider_name: str | None = None
        is_custom = False
        match provider.name:
            case ModelProviderName.openrouter:
                litellm_provider_name = "openrouter"
            case ModelProviderName.openai:
                litellm_provider_name = "openai"
            case ModelProviderName.groq:
                litellm_provider_name = "groq"
            case ModelProviderName.anthropic:
                litellm_provider_name = "anthropic"
            case ModelProviderName.ollama:
                # We don't let litellm use the Ollama API and muck with our requests. We use Ollama's OpenAI compatible API.
                # This is because we're setting detailed features like response_format=json_schema and want lower level control.
                is_custom = True
            case ModelProviderName.gemini_api:
                litellm_provider_name = "gemini"
            case ModelProviderName.fireworks_ai:
                litellm_provider_name = "fireworks_ai"
            case ModelProviderName.amazon_bedrock:
                litellm_provider_name = "bedrock"
            case ModelProviderName.azure_openai:
                litellm_provider_name = "azure"
            case ModelProviderName.huggingface:
                litellm_provider_name = "huggingface"
            case ModelProviderName.vertex:
                litellm_provider_name = "vertex_ai"
            case ModelProviderName.together_ai:
                litellm_provider_name = "together_ai"
            case ModelProviderName.openai_compatible:
                is_custom = True
            case ModelProviderName.kiln_custom_registry:
                is_custom = True
            case ModelProviderName.kiln_fine_tune:
                is_custom = True
            case _:
                raise_exhaustive_enum_error(provider.name)

        if is_custom:
            if self._api_base is None:
                raise ValueError(
                    "Explicit Base URL is required for OpenAI compatible APIs (custom models, ollama, fine tunes, and custom registry models)"
                )
            # Use openai as it's only used for format, not url
            litellm_provider_name = "openai"

        # Sholdn't be possible but keep type checker happy
        if litellm_provider_name is None:
            raise ValueError(
                f"Provider name could not lookup valid litellm provider ID {provider.model_id}"
            )

        self._litellm_model_id = litellm_provider_name + "/" + provider.model_id
        return self._litellm_model_id

    async def build_completion_kwargs(
        self,
        provider: KilnModelProvider,
        messages: list[dict[str, Any]],
        top_logprobs: int | None,
    ) -> dict[str, Any]:
        extra_body = self.build_extra_body(provider)

        # Merge all parameters into a single kwargs dict for litellm
        completion_kwargs = {
            "model": self.litellm_model_id(),
            "messages": messages,
            "api_base": self._api_base,
            "headers": self._headers,
            **extra_body,
            **self._additional_body_options,
        }

        # Response format: json_schema, json_instructions, json_mode, function_calling, etc
        response_format_options = await self.response_format_options()
        completion_kwargs.update(response_format_options)

        if top_logprobs is not None:
            completion_kwargs["logprobs"] = True
            completion_kwargs["top_logprobs"] = top_logprobs

        return completion_kwargs
