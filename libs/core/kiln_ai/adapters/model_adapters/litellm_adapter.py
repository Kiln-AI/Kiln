import copy
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, TypeAlias, Union

import litellm
from litellm.types.utils import (
    ChatCompletionMessageToolCall,
    ChoiceLogprobs,
    Choices,
    ModelResponse,
)
from litellm.types.utils import (
    Message as LiteLLMMessage,
)
from litellm.types.utils import Usage as LiteLlmUsage
from openai.types.chat import (
    ChatCompletionToolMessageParam,
)
from openai.types.chat.chat_completion_message_tool_call_param import (
    ChatCompletionMessageToolCallParam,
)

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.ml_model_list import (
    KilnModelProvider,
    ModelProviderName,
    StructuredOutputMode,
)
from kiln_ai.adapters.model_adapters.base_adapter import (
    AdapterConfig,
    BaseAdapter,
    RunOutput,
    Usage,
)
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel.json_schema import validate_schema_with_value_error
from kiln_ai.tools.base_tool import KilnToolInterface
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_ai.utils.open_ai_types import (
    ChatCompletionAssistantMessageParamWrapper,
    ChatCompletionMessageParam,
)

MAX_CALLS_PER_TURN = 10
MAX_TOOL_CALLS_PER_TURN = 30

logger = logging.getLogger(__name__)

ChatCompletionMessageIncludingLiteLLM: TypeAlias = Union[
    ChatCompletionMessageParam, LiteLLMMessage
]


@dataclass
class ModelTurnResult:
    assistant_message: str
    all_messages: list[ChatCompletionMessageIncludingLiteLLM]
    model_response: ModelResponse | None
    model_choice: Choices | None
    usage: Usage


class LiteLlmAdapter(BaseAdapter):
    def __init__(
        self,
        config: LiteLlmConfig,
        kiln_task: datamodel.Task,
        base_adapter_config: AdapterConfig | None = None,
    ):
        self.config = config
        self._additional_body_options = config.additional_body_options
        self._api_base = config.base_url
        self._headers = config.default_headers
        self._litellm_model_id: str | None = None
        self._cached_available_tools: list[KilnToolInterface] | None = None

        super().__init__(
            task=kiln_task,
            run_config=config.run_config_properties,
            config=base_adapter_config,
        )

    async def _run_model_turn(
        self,
        provider: KilnModelProvider,
        prior_messages: list[ChatCompletionMessageIncludingLiteLLM],
        top_logprobs: int | None,
        skip_response_format: bool,
    ) -> ModelTurnResult:
        """
        Call the model for a single top level turn: from user message to agent message.

        It may make handle iterations of tool calls between the user/agent message if needed.
        """

        usage = Usage()
        messages = list(prior_messages)
        tool_calls_count = 0

        while tool_calls_count < MAX_TOOL_CALLS_PER_TURN:
            # Build completion kwargs for tool calls
            completion_kwargs = await self.build_completion_kwargs(
                provider,
                # Pass a copy, as acompletion mutates objects and breaks types.
                copy.deepcopy(messages),
                top_logprobs,
                skip_response_format,
            )

            # Make the completion call
            model_response, response_choice = await self.acompletion_checking_response(
                **completion_kwargs
            )

            # count the usage
            usage += self.usage_from_response(model_response)

            # Extract content and tool calls
            if not hasattr(response_choice, "message"):
                raise ValueError("Response choice has no message")
            content = response_choice.message.content
            tool_calls = response_choice.message.tool_calls
            if not content and not tool_calls:
                raise ValueError(
                    "Model returned an assistant message, but no content or tool calls. This is not supported."
                )

            # Add message to messages, so it can be used in the next turn
            messages.append(response_choice.message)

            # Process tool calls if any
            if tool_calls and len(tool_calls) > 0:
                (
                    assistant_message_from_toolcall,
                    tool_call_messages,
                ) = await self.process_tool_calls(tool_calls)

                # Add tool call results to messages
                messages.extend(tool_call_messages)

                # If task_response tool was called, we're done
                if assistant_message_from_toolcall is not None:
                    return ModelTurnResult(
                        assistant_message=assistant_message_from_toolcall,
                        all_messages=messages,
                        model_response=model_response,
                        model_choice=response_choice,
                        usage=usage,
                    )

                # If there were tool calls, increment counter and continue
                if tool_call_messages:
                    tool_calls_count += 1
                    continue

            # If no tool calls, return the content as final output
            if content:
                return ModelTurnResult(
                    assistant_message=content,
                    all_messages=messages,
                    model_response=model_response,
                    model_choice=response_choice,
                    usage=usage,
                )

            # If we get here with no content and no tool calls, break
            raise RuntimeError(
                "Model returned neither content nor tool calls. It must return at least one of these."
            )

        raise RuntimeError(
            f"Too many tool calls ({tool_calls_count}). Stopping iteration to avoid using too many tokens."
        )

    async def _run(self, input: Dict | str) -> tuple[RunOutput, Usage | None]:
        usage = Usage()

        provider = self.model_provider()
        if not provider.model_id:
            raise ValueError("Model ID is required for OpenAI compatible models")

        chat_formatter = self.build_chat_formatter(input)
        messages: list[ChatCompletionMessageIncludingLiteLLM] = []

        prior_output: str | None = None
        final_choice: Choices | None = None
        turns = 0

        while True:
            turns += 1
            if turns > MAX_CALLS_PER_TURN:
                raise RuntimeError(
                    f"Too many turns ({turns}). Stopping iteration to avoid using too many tokens."
                )

            turn = chat_formatter.next_turn(prior_output)
            if turn is None:
                # No next turn, we're done
                break

            # Add messages from the turn to chat history
            for message in turn.messages:
                if message.content is None:
                    raise ValueError("Empty message content isn't allowed")
                # pyright incorrectly warns about this, but it's valid so we can ignore. It can't handle the multi-value role.
                messages.append({"role": message.role, "content": message.content})  # type: ignore

            skip_response_format = not turn.final_call
            turn_result = await self._run_model_turn(
                provider,
                messages,
                self.base_adapter_config.top_logprobs if turn.final_call else None,
                skip_response_format,
            )

            usage += turn_result.usage

            prior_output = turn_result.assistant_message
            messages = turn_result.all_messages
            final_choice = turn_result.model_choice

            if not prior_output:
                raise RuntimeError("No assistant message/output returned from model")

        logprobs = self._extract_and_validate_logprobs(final_choice)

        # Save COT/reasoning if it exists. May be a message, or may be parsed by LiteLLM (or openrouter, or anyone upstream)
        intermediate_outputs = chat_formatter.intermediate_outputs()
        self._extract_reasoning_to_intermediate_outputs(
            final_choice, intermediate_outputs
        )

        if not isinstance(prior_output, str):
            raise RuntimeError(f"assistant message is not a string: {prior_output}")

        trace = self.all_messages_to_trace(messages)
        output = RunOutput(
            output=prior_output,
            intermediate_outputs=intermediate_outputs,
            output_logprobs=logprobs,
            trace=trace,
        )

        return output, usage

    def _extract_and_validate_logprobs(
        self, final_choice: Choices | None
    ) -> ChoiceLogprobs | None:
        """
        Extract logprobs from the final choice and validate they exist if required.
        """
        logprobs = None
        if (
            final_choice is not None
            and hasattr(final_choice, "logprobs")
            and isinstance(final_choice.logprobs, ChoiceLogprobs)
        ):
            logprobs = final_choice.logprobs

        # Check logprobs worked, if required
        if self.base_adapter_config.top_logprobs is not None and logprobs is None:
            raise RuntimeError("Logprobs were required, but no logprobs were returned.")

        return logprobs

    def _extract_reasoning_to_intermediate_outputs(
        self, final_choice: Choices | None, intermediate_outputs: Dict[str, Any]
    ) -> None:
        """Extract reasoning content from model choice and add to intermediate outputs if present."""
        if (
            final_choice is not None
            and hasattr(final_choice, "message")
            and hasattr(final_choice.message, "reasoning_content")
        ):
            reasoning_content = final_choice.message.reasoning_content
            if reasoning_content is not None:
                stripped_reasoning_content = reasoning_content.strip()
                if len(stripped_reasoning_content) > 0:
                    intermediate_outputs["reasoning"] = stripped_reasoning_content

    async def acompletion_checking_response(
        self, **kwargs
    ) -> Tuple[ModelResponse, Choices]:
        response = await litellm.acompletion(**kwargs)
        if (
            not isinstance(response, ModelResponse)
            or not response.choices
            or len(response.choices) == 0
            or not isinstance(response.choices[0], Choices)
        ):
            raise RuntimeError(
                f"Expected ModelResponse with Choices, got {type(response)}."
            )
        return response, response.choices[0]

    def adapter_name(self) -> str:
        return "kiln_openai_compatible_adapter"

    async def response_format_options(self) -> dict[str, Any]:
        # Unstructured if task isn't structured
        if not self.has_structured_output():
            return {}

        structured_output_mode = self.run_config.structured_output_mode

        match structured_output_mode:
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
                provider_name = self.run_config.model_provider_name
                if provider_name == ModelProviderName.ollama:
                    # Ollama added json_schema to all models: https://ollama.com/blog/structured-outputs
                    return self.json_schema_response_format()
                elif provider_name == ModelProviderName.docker_model_runner:
                    # Docker Model Runner uses OpenAI-compatible API with JSON schema support
                    return self.json_schema_response_format()
                else:
                    # Default to function calling -- it's older than the other modes. Higher compatibility.
                    # Strict isn't widely supported yet, so we don't use it by default unless it's OpenAI.
                    strict = provider_name == ModelProviderName.openai
                    return self.tool_call_params(strict=strict)
            case StructuredOutputMode.unknown:
                # See above, but this case should never happen.
                raise ValueError("Structured output mode is unknown.")
            case _:
                raise_exhaustive_enum_error(structured_output_mode)

    def json_schema_response_format(self) -> dict[str, Any]:
        output_schema = self.task.output_schema()
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
        output_schema = self.task.output_schema()
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
        # Don't love having this logic here. But it's worth the usability improvement
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

        if provider.gemini_reasoning_enabled:
            extra_body["reasoning"] = {
                "enabled": True,
            }

        if provider.name == ModelProviderName.openrouter:
            # Ask OpenRouter to include usage in the response (cost)
            extra_body["usage"] = {"include": True}

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

        # Siliconflow uses a bool flag for thinking, for some models
        if provider.siliconflow_enable_thinking is not None:
            extra_body["enable_thinking"] = provider.siliconflow_enable_thinking

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
            case ModelProviderName.docker_model_runner:
                # Docker Model Runner uses OpenAI-compatible API, similar to Ollama
                # We want direct control over the requests for features like response_format=json_schema
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
            case ModelProviderName.cerebras:
                litellm_provider_name = "cerebras"
            case ModelProviderName.siliconflow_cn:
                is_custom = True
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
        messages: list[ChatCompletionMessageIncludingLiteLLM],
        top_logprobs: int | None,
        skip_response_format: bool = False,
    ) -> dict[str, Any]:
        extra_body = self.build_extra_body(provider)

        # Merge all parameters into a single kwargs dict for litellm
        completion_kwargs = {
            "model": self.litellm_model_id(),
            "messages": messages,
            "api_base": self._api_base,
            "headers": self._headers,
            "temperature": self.run_config.temperature,
            "top_p": self.run_config.top_p,
            # This drops params that are not supported by the model. Only openai params like top_p, temperature -- not litellm params like model, etc.
            # Not all models and providers support all openai params (for example, o3 doesn't support top_p)
            # Better to ignore them than to fail the model call.
            # https://docs.litellm.ai/docs/completion/input
            "drop_params": True,
            **extra_body,
            **self._additional_body_options,
        }

        tool_calls = await self.litellm_tools()
        has_tools = len(tool_calls) > 0
        if has_tools:
            completion_kwargs["tools"] = tool_calls
            completion_kwargs["tool_choice"] = "auto"

        if not skip_response_format:
            # Response format: json_schema, json_instructions, json_mode, function_calling, etc
            response_format_options = await self.response_format_options()

            # Check for a conflict between tools and response format using tools
            # We could reconsider this. Model could be able to choose between a final answer or a tool call on any turn. However, good models for tools tend to also support json_schea, so do we need to support both? If we do, merge them, and consider auto vs forced when merging (only forced for final, auto for merged).
            if has_tools and "tools" in response_format_options:
                raise ValueError(
                    "Function calling/tools can't be used as the JSON response format if you're also using tools. Please select a different structured output mode."
                )

            completion_kwargs.update(response_format_options)

        if top_logprobs is not None:
            completion_kwargs["logprobs"] = True
            completion_kwargs["top_logprobs"] = top_logprobs

        return completion_kwargs

    def usage_from_response(self, response: ModelResponse) -> Usage:
        litellm_usage = response.get("usage", None)

        # LiteLLM isn't consistent in how it returns the cost.
        cost = response._hidden_params.get("response_cost", None)
        if cost is None and litellm_usage:
            cost = litellm_usage.get("cost", None)

        usage = Usage()

        if not litellm_usage and not cost:
            return usage

        if litellm_usage and isinstance(litellm_usage, LiteLlmUsage):
            usage.input_tokens = litellm_usage.get("prompt_tokens", None)
            usage.output_tokens = litellm_usage.get("completion_tokens", None)
            usage.total_tokens = litellm_usage.get("total_tokens", None)
        else:
            logger.warning(
                f"Unexpected usage format from litellm: {litellm_usage}. Expected Usage object, got {type(litellm_usage)}"
            )

        if isinstance(cost, float):
            usage.cost = cost
        elif cost is not None:
            # None is allowed, but no other types are expected
            logger.warning(
                f"Unexpected cost format from litellm: {cost}. Expected float, got {type(cost)}"
            )

        return usage

    async def cached_available_tools(self) -> list[KilnToolInterface]:
        if self._cached_available_tools is None:
            self._cached_available_tools = await self.available_tools()
        return self._cached_available_tools

    async def litellm_tools(self) -> list[Dict]:
        available_tools = await self.cached_available_tools()

        # LiteLLM takes the standard OpenAI-compatible tool call format
        return [await tool.toolcall_definition() for tool in available_tools]

    async def process_tool_calls(
        self, tool_calls: list[ChatCompletionMessageToolCall] | None
    ) -> tuple[str | None, list[ChatCompletionToolMessageParam]]:
        if tool_calls is None:
            return None, []

        assistant_output_from_toolcall: str | None = None
        tool_call_response_messages: list[ChatCompletionToolMessageParam] = []

        for tool_call in tool_calls:
            # Kiln "task_response" tool is used for returning structured output via tool calls.
            # Load the output from the tool call. Also
            if tool_call.function.name == "task_response":
                assistant_output_from_toolcall = tool_call.function.arguments
                continue

            # Process normal tool calls (not the "task_response" tool)
            tool_name = tool_call.function.name
            tool = None
            for tool_option in await self.cached_available_tools():
                if await tool_option.name() == tool_name:
                    tool = tool_option
                    break
            if not tool:
                raise RuntimeError(
                    f"A tool named '{tool_name}' was invoked by a model, but was not available."
                )

            # Parse the arguments and validate them against the tool's schema
            try:
                parsed_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"Failed to parse arguments for tool '{tool_name}' (should be JSON): {tool_call.function.arguments}"
                )
            try:
                tool_call_definition = await tool.toolcall_definition()
                json_schema = json.dumps(tool_call_definition["function"]["parameters"])
                validate_schema_with_value_error(parsed_args, json_schema)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to validate arguments for tool '{tool_name}'. The arguments didn't match the tool's schema. The arguments were: {parsed_args}\n The error was: {e}"
                ) from e

            result = await tool.run(**parsed_args)

            tool_call_response_messages.append(
                ChatCompletionToolMessageParam(
                    role="tool",
                    tool_call_id=tool_call.id,
                    content=result,
                )
            )

        if (
            assistant_output_from_toolcall is not None
            and len(tool_call_response_messages) > 0
        ):
            raise RuntimeError(
                "Model asked for impossible combination: task_response tool call and other tool calls were both provided in the same turn. This is not supported as it means the model asked us to both return task_response results (ending the turn) and run new tools calls to send back to the model. If the model makes this mistake often, try a difference structured data model like JSON schema, where this is impossible."
            )

        return assistant_output_from_toolcall, tool_call_response_messages

    def litellm_message_to_trace_message(
        self, raw_message: LiteLLMMessage
    ) -> ChatCompletionAssistantMessageParamWrapper:
        """
        Convert a LiteLLM Message object to an OpenAI compatible message, our ChatCompletionAssistantMessageParamWrapper
        """
        message: ChatCompletionAssistantMessageParamWrapper = {
            "role": "assistant",
        }
        if raw_message.role != "assistant":
            raise ValueError(
                "Model returned a message with a role other than assistant. This is not supported."
            )

        if hasattr(raw_message, "content"):
            message["content"] = raw_message.content
        if hasattr(raw_message, "reasoning_content"):
            message["reasoning_content"] = raw_message.reasoning_content
        if hasattr(raw_message, "tool_calls"):
            # Convert ChatCompletionMessageToolCall to ChatCompletionMessageToolCallParam
            open_ai_tool_calls: List[ChatCompletionMessageToolCallParam] = []
            for litellm_tool_call in raw_message.tool_calls or []:
                # Optional in the SDK for streaming responses, but should never be None at this point.
                if litellm_tool_call.function.name is None:
                    raise ValueError(
                        "The model requested a tool call, without providing a function name (required)."
                    )
                open_ai_tool_calls.append(
                    ChatCompletionMessageToolCallParam(
                        id=litellm_tool_call.id,
                        type="function",
                        function={
                            "name": litellm_tool_call.function.name,
                            "arguments": litellm_tool_call.function.arguments,
                        },
                    )
                )
            if len(open_ai_tool_calls) > 0:
                message["tool_calls"] = open_ai_tool_calls

        if not message.get("content") and not message.get("tool_calls"):
            raise ValueError(
                "Model returned an assistant message, but no content or tool calls. This is not supported."
            )

        return message

    def all_messages_to_trace(
        self, messages: list[ChatCompletionMessageIncludingLiteLLM]
    ) -> list[ChatCompletionMessageParam]:
        """
        Internally we allow LiteLLM Message objects, but for trace we need OpenAI compatible types. Replace LiteLLM Message objects with OpenAI compatible types.
        """
        trace: list[ChatCompletionMessageParam] = []
        for message in messages:
            if isinstance(message, LiteLLMMessage):
                trace.append(self.litellm_message_to_trace_message(message))
            else:
                trace.append(message)
        return trace
