from typing import Any, Dict

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

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
from kiln_ai.adapters.model_adapters.openai_compatible_config import (
    OpenAICompatibleConfig,
)
from kiln_ai.adapters.parsers.json_parser import parse_json_string
from kiln_ai.datamodel import PromptGenerators, PromptId
from kiln_ai.datamodel.task import RunConfig
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


class OpenAICompatibleAdapter(BaseAdapter):
    def __init__(
        self,
        config: OpenAICompatibleConfig,
        kiln_task: datamodel.Task,
        prompt_id: PromptId | None = None,
        base_adapter_config: AdapterConfig | None = None,
    ):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            default_headers=config.default_headers,
        )

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
        intermediate_outputs: dict[str, str] = {}
        prompt = self.build_prompt()
        user_msg = self.prompt_builder.build_user_message(input)
        messages = [
            ChatCompletionSystemMessageParam(role="system", content=prompt),
            ChatCompletionUserMessageParam(role="user", content=user_msg),
        ]

        run_strategy, cot_prompt = self.run_strategy()

        if run_strategy == "cot_as_message":
            if not cot_prompt:
                raise ValueError("cot_prompt is required for cot_as_message strategy")
            messages.append(
                ChatCompletionSystemMessageParam(role="system", content=cot_prompt)
            )
        elif run_strategy == "cot_two_call":
            if not cot_prompt:
                raise ValueError("cot_prompt is required for cot_two_call strategy")
            messages.append(
                ChatCompletionSystemMessageParam(role="system", content=cot_prompt)
            )

            # First call for chain of thought
            cot_response = await self.client.chat.completions.create(
                model=provider.provider_options["model"],
                messages=messages,
            )
            cot_content = cot_response.choices[0].message.content
            if cot_content is not None:
                intermediate_outputs["chain_of_thought"] = cot_content

            messages.extend(
                [
                    ChatCompletionAssistantMessageParam(
                        role="assistant", content=cot_content
                    ),
                    ChatCompletionUserMessageParam(
                        role="user",
                        content=COT_FINAL_ANSWER_PROMPT,
                    ),
                ]
            )

        # Build custom request params based on model provider
        extra_body = self.build_extra_body(provider)

        # Main completion call
        response_format_options = await self.response_format_options()
        response = await self.client.chat.completions.create(
            model=provider.provider_options["model"],
            messages=messages,
            extra_body=extra_body,
            logprobs=self.base_adapter_config.top_logprobs is not None,
            top_logprobs=self.base_adapter_config.top_logprobs,
            **response_format_options,
        )

        if not isinstance(response, ChatCompletion):
            raise RuntimeError(
                f"Expected ChatCompletion response, got {type(response)}."
            )

        if hasattr(response, "error") and response.error:  # pyright: ignore
            raise RuntimeError(
                f"OpenAI compatible API returned status code {response.error.get('code')}: {response.error.get('message') or 'Unknown error'}.\nError: {response.error}"  # pyright: ignore
            )
        if not response.choices or len(response.choices) == 0:
            raise RuntimeError(
                "No message content returned in the response from OpenAI compatible API"
            )

        message = response.choices[0].message
        logprobs = response.choices[0].logprobs

        # Check logprobs worked, if requested
        if self.base_adapter_config.top_logprobs is not None and logprobs is None:
            raise RuntimeError("Logprobs were required, but no logprobs were returned.")

        # Save reasoning if it exists (OpenRouter specific api response field)
        if provider.require_openrouter_reasoning:
            if (
                hasattr(message, "reasoning") and message.reasoning  # pyright: ignore
            ):
                intermediate_outputs["reasoning"] = message.reasoning  # pyright: ignore
            else:
                raise RuntimeError(
                    "Reasoning is required for this model, but no reasoning was returned from OpenRouter."
                )

        # the string content of the response
        response_content = message.content

        # Fallback: Use args of first tool call to task_response if it exists
        if not response_content and message.tool_calls:
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

        # Parse to dict if we have structured output
        output: Dict | str = response_content
        if self.has_structured_output():
            output = parse_json_string(response_content)

        return RunOutput(
            output=output,
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
            case StructuredOutputMode.function_calling_weak:
                return self.tool_call_params(strict=False)
            case StructuredOutputMode.function_calling:
                return self.tool_call_params(strict=True)
            case StructuredOutputMode.json_instructions:
                # JSON done via instructions in prompt, not the API response format. Do not ask for json_object (see option below).
                return {}
            case StructuredOutputMode.json_instruction_and_object:
                # We set response_format to json_object and also set json instructions in the prompt
                return {"response_format": {"type": "json_object"}}
            case StructuredOutputMode.default:
                # Default to function calling -- it's older than the other modes. Higher compatibility.
                return self.tool_call_params(strict=True)
            case _:
                raise_exhaustive_enum_error(provider.structured_output_mode)

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

        if provider.require_openrouter_reasoning:
            # https://openrouter.ai/docs/use-cases/reasoning-tokens
            extra_body["reasoning"] = {
                "exclude": False,
            }

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
