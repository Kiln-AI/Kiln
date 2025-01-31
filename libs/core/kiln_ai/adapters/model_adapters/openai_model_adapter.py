from typing import Any, Dict, NoReturn

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion import Choice

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.ml_model_list import StructuredOutputMode
from kiln_ai.adapters.model_adapters.base_adapter import (
    AdapterInfo,
    BaseAdapter,
    BasePromptBuilder,
    RunOutput,
)
from kiln_ai.adapters.parsers.json_parser import parse_json_string


class OpenAICompatibleAdapter(BaseAdapter):
    def __init__(
        self,
        api_key: str,
        kiln_task: datamodel.Task,
        model_name: str,
        provider_name: str,
        base_url: str | None = None,  # Client will default to OpenAI
        default_headers: dict[str, str] | None = None,
        prompt_builder: BasePromptBuilder | None = None,
        tags: list[str] | None = None,
    ):
        if not model_name or not provider_name:
            raise ValueError(
                "model_name and provider_name must be provided for OpenAI compatible adapter"
            )

        # Create an async OpenAI client instead
        self.client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, default_headers=default_headers
        )

        super().__init__(
            kiln_task,
            model_name=model_name,
            model_provider_name=provider_name,
            prompt_builder=prompt_builder,
            tags=tags,
        )

    async def _run(self, input: Dict | str) -> RunOutput:
        provider = await self.model_provider()

        intermediate_outputs: dict[str, str] = {}

        prompt = await self.build_prompt()
        user_msg = self.prompt_builder.build_user_message(input)
        messages = [
            ChatCompletionSystemMessageParam(role="system", content=prompt),
            ChatCompletionUserMessageParam(role="user", content=user_msg),
        ]

        # Handle chain of thought if enabled
        cot_prompt = self.prompt_builder.chain_of_thought_prompt()
        if cot_prompt and self.has_structured_output():
            # TODO P0: Fix COT
            messages.append({"role": "system", "content": cot_prompt})

            # First call for chain of thought
            cot_response = await self.client.chat.completions.create(
                model=self.model_name,
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
                    ChatCompletionSystemMessageParam(
                        role="system",
                        content="Considering the above, return a final result.",
                    ),
                ]
            )
        elif cot_prompt:
            messages.append({"role": "system", "content": cot_prompt})
        else:
            intermediate_outputs = {}

        # Main completion call
        response_format_options = await self.response_format_options()
        print(f"response_format_options: {response_format_options}")
        response = await self.client.chat.completions.create(
            model=provider.provider_options["model"],
            messages=messages,
            # TODO P0: remove this
            extra_body={"include_reasoning": True},
            **response_format_options,
        )
        print(f"response: {response}")
        if not isinstance(response, ChatCompletion):
            raise RuntimeError(
                f"Expected ChatCompletion response, got {type(response)}."
            )

        if hasattr(response, "error") and response.error:  # pyright: ignore
            raise RuntimeError(
                f"OpenAI compatible API returned status code {response.error.get('code')}: {response.error.get('message') or 'Unknown error'}."  # pyright: ignore
            )
        if not response.choices or len(response.choices) == 0:
            raise RuntimeError(
                "No message content returned in the response from OpenAI compatible API"
            )

        message = response.choices[0].message

        # Save reasoning if it exists
        if hasattr(message, "reasoning") and message.reasoning:  # pyright: ignore
            intermediate_outputs["reasoning"] = message.reasoning  # pyright: ignore

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

        if self.has_structured_output():
            structured_response = parse_json_string(response_content)
            return RunOutput(
                output=structured_response,
                intermediate_outputs=intermediate_outputs,
            )

        return RunOutput(
            output=response_content,
            intermediate_outputs=intermediate_outputs,
        )

    def adapter_info(self) -> AdapterInfo:
        return AdapterInfo(
            model_name=self.model_name,
            model_provider=self.model_provider_name,
            adapter_name="kiln_openai_compatible_adapter",
            prompt_builder_name=self.prompt_builder.__class__.prompt_builder_name(),
            prompt_id=self.prompt_builder.prompt_id(),
        )

    async def response_format_options(self) -> dict[str, Any]:
        # Unstructured if task isn't structured
        if not self.has_structured_output():
            return {}

        provider = await self.model_provider()
        # TODO check these
        match provider.structured_output_mode:
            case StructuredOutputMode.json_mode:
                return {"response_format": {"type": "json_object"}}
            case StructuredOutputMode.json_schema:
                # TODO P0: use json_schema
                output_schema = self.kiln_task.output_schema()
                print(f"output_schema: {output_schema}")
                return {
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "task_response",
                            "schema": output_schema,
                        },
                    }
                }
            case StructuredOutputMode.function_calling:
                # TODO P0
                return self.tool_call_params()
            case StructuredOutputMode.json_instructions:
                # JSON done via instructions in prompt, not the API response format
                # TODO try json_object on stable API
                return {}
            case StructuredOutputMode.json_instruction_and_object:
                # We set response_format to json_object, but we also need to set the instructions in the prompt
                return {"response_format": {"type": "json_object"}}
            case StructuredOutputMode.default:
                # Default to function calling -- it's older than the other modes
                return self.tool_call_params()
            case _:
                raise ValueError(
                    f"Unsupported structured output mode: {provider.structured_output_mode}"
                )
                # pyright will detect missing cases with this
                return NoReturn

    def tool_call_params(self) -> dict[str, Any]:
        return {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "task_response",
                        "parameters": self.kiln_task.output_schema(),
                        "strict": True,
                    },
                }
            ],
            "tool_choice": {
                "type": "function",
                "function": {"name": "task_response"},
            },
        }
