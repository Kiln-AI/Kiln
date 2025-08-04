import json
import logging
from typing import Any, Dict, List, Tuple

import litellm
from litellm.types.utils import (
    ChatCompletionMessageToolCall,
    ChoiceLogprobs,
    Choices,
    ModelResponse,
)
from litellm.types.utils import Usage as LiteLlmUsage

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
from kiln_ai.datamodel.task import run_config_from_run_config_properties
from kiln_ai.tools.base_tool import KilnTool
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

MAX_CALLS_PER_TURN = 10
MAX_TOOL_CALLS_PER_TURN = 30

logger = logging.getLogger(__name__)


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
        self._cached_available_tools: list[KilnTool] | None = None

        # Create a RunConfig, adding the task to the RunConfigProperties
        run_config = run_config_from_run_config_properties(
            task=kiln_task,
            run_config_properties=config.run_config_properties,
        )

        super().__init__(
            run_config=run_config,
            config=base_adapter_config,
        )

    async def _run_model_turn(
        self,
        provider: KilnModelProvider,
        prior_messages: list[dict[str, Any]],
        top_logprobs: int | None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Call the model for a single top level turn (user message to agent message with content).

        It may make handle iterations of tool calls if needed.
        """

        messages = list(prior_messages)
        tool_calls_count = 0

        while tool_calls_count < MAX_TOOL_CALLS_PER_TURN:
            # Build completion kwargs for tool calls
            completion_kwargs = await self.build_completion_kwargs(
                provider,
                messages,
                top_logprobs,
                skip_response_format=True,  # Don't use structured output for tool calls
            )

            # Set tool choice to auto to allow model to choose between tool calls and final response
            completion_kwargs["tool_choice"] = "auto"

            # Make the completion call
            response, response_choice = await self.acompletion_checking_response(
                **completion_kwargs
            )

            # Extract content and tool_calls safely
            content = None
            tool_calls = None
            if hasattr(response_choice, "message"):
                if hasattr(response_choice.message, "content"):
                    content = response_choice.message.content
                if hasattr(response_choice.message, "tool_calls"):
                    tool_calls = response_choice.message.tool_calls

            # Add the assistant's response to messages
            assistant_message = {
                "role": "assistant",
                "content": content,
                # TODO: ensure structure
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

            # Process tool calls if any
            if tool_calls:
                prior_output_from_toolcall, tool_call_messages = (
                    self.process_tool_calls(tool_calls)
                )

                # Add tool call results to messages
                messages.extend(tool_call_messages)

                # If task_response tool was called, we're done
                if prior_output_from_toolcall is not None:
                    return prior_output_from_toolcall, messages

                # If there were tool calls, increment counter and continue
                if tool_call_messages:
                    tool_calls_count += 1
                    continue

            # If no tool calls, return the content as final output
            if content:
                return content, messages

            # If we get here with no content and no tool calls, break
            break

        raise RuntimeError(
            f"Too many tool calls ({tool_calls_count}). Stopping iteration to avoid using too many tokens."
        )

    async def _run(self, input: Dict | str) -> tuple[RunOutput, Usage | None]:
        provider = self.model_provider()
        if not provider.model_id:
            raise ValueError("Model ID is required for OpenAI compatible models")

        chat_formatter = self.build_chat_formatter(input)
        messages = []

        prior_output = None
        prior_message = None
        response = None
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
                messages.append({"role": message.role, "content": message.content})

            skip_response_format = not turn.final_call
            completion_kwargs = await self.build_completion_kwargs(
                provider,
                messages,
                self.base_adapter_config.top_logprobs if turn.final_call else None,
                skip_response_format,
            )

            # If this is the final call and we have tools available, handle tool calls in a loop
            if turn.final_call and self.litellm_tools():
                prior_output, updated_messages = await self._run_model_turn(
                    provider,
                    messages,
                    self.base_adapter_config.top_logprobs,
                )
                messages = updated_messages
                break  # We're done after handling tool calls
            else:
                # Regular completion call
                response, response_choice = await self.acompletion_checking_response(
                    **completion_kwargs
                )
                message = getattr(response_choice, "message", None)
                prior_output = getattr(message, "content", None) if message else None

                # Add the assistant's response to chat history
                messages.append(
                    {
                        "role": "assistant",
                        "content": prior_output,
                        "tool_calls": getattr(message, "tool_calls", None)
                        if message
                        else None,
                    }
                )

            if not prior_output:
                raise RuntimeError("No output returned from model")

        # Get the final response from the chat formatter
        intermediate_outputs = chat_formatter.intermediate_outputs()

        # Get the last response to extract logprobs and reasoning if needed
        final_response = None
        final_choice = None
        if response is not None:
            final_response = response
            if response.choices and len(response.choices) > 0:
                final_choice = response.choices[0]
        else:
            # If we only used tool calls, we need to get logprobs and reasoning from the last message
            # This is a limitation of the current approach - we can't get logprobs from tool call responses
            # We would need to make an additional call to get logprobs if needed
            pass

        logprobs = None
        if final_choice is not None:
            if hasattr(final_choice, "logprobs") and isinstance(
                final_choice.logprobs, ChoiceLogprobs
            ):
                logprobs = final_choice.logprobs

        # Check logprobs worked, if requested
        if self.base_adapter_config.top_logprobs is not None and logprobs is None:
            raise RuntimeError("Logprobs were required, but no logprobs were returned.")

        # Save reasoning if it exists and was parsed by LiteLLM (or openrouter, or anyone upstream)
        reasoning_content = None
        if final_choice is not None:
            final_choice_message = getattr(final_choice, "message", None)
            if final_choice_message and hasattr(
                final_choice_message, "reasoning_content"
            ):
                reasoning_content = getattr(
                    final_choice_message, "reasoning_content", None
                )
        elif prior_message is not None:
            prior_message_message = getattr(prior_message, "message", None)
            if prior_message_message and hasattr(
                prior_message_message, "reasoning_content"
            ):
                reasoning_content = getattr(
                    prior_message_message, "reasoning_content", None
                )

        if reasoning_content is not None and len(reasoning_content.strip()) > 0:
            intermediate_outputs["reasoning"] = reasoning_content.strip()

        # the string content of the response
        response_content = prior_output

        if not isinstance(response_content, str):
            raise RuntimeError(f"response is not a string: {response_content}")

        return RunOutput(
            output=response_content,
            intermediate_outputs=intermediate_outputs,
            output_logprobs=logprobs,
            trace=messages,
        ), self.usage_from_response(
            final_response
        ) if final_response is not None else None

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

        tool_calls = self.litellm_tools()
        has_tools = len(tool_calls) > 0
        if has_tools:
            completion_kwargs["tools"] = tool_calls
            completion_kwargs["tool_choice"] = "auto"

        if not skip_response_format:
            # Response format: json_schema, json_instructions, json_mode, function_calling, etc
            response_format_options = await self.response_format_options()

            # TODO: maybe reconsider this. Model should be able to choose between a final answer or a tool call on any turn. But good models have json_schea, so do we need to support both? If we do, merge them, and consider auto vs forced when merging (only forced for final, auto for merged).
            # Check for a conflict between tools and response format using tools
            if has_tools and "tools" in response_format_options:
                raise ValueError(
                    "Function calling/tools can't be used as the JSON response format if you're also using tools. Please select a different structured output mode."
                )

            completion_kwargs.update(response_format_options)

        if top_logprobs is not None:
            completion_kwargs["logprobs"] = True
            completion_kwargs["top_logprobs"] = top_logprobs

        return completion_kwargs

    def usage_from_response(self, response: ModelResponse) -> Usage | None:
        litellm_usage = response.get("usage", None)

        # LiteLLM isn't consistent in how it returns the cost.
        cost = response._hidden_params.get("response_cost", None)
        if cost is None and litellm_usage:
            cost = litellm_usage.get("cost", None)

        if not litellm_usage and not cost:
            return None

        usage = Usage()

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

    def cached_available_tools(self) -> list[KilnTool]:
        if self._cached_available_tools is None:
            self._cached_available_tools = self.available_tools()
        return self._cached_available_tools

    def litellm_tools(self) -> list[Dict]:
        available_tools = self.cached_available_tools()

        # LiteLLM takes the standard OpenAI-compatible tool call format
        return [tool.toolcall_definition() for tool in available_tools]

    def process_tool_calls(
        self, tool_calls: List[ChatCompletionMessageToolCall] | None
    ) -> tuple[str | None, list[Dict]]:
        prior_output_from_toolcall: str | None = None
        tool_call_messages: list[Dict] = []

        if tool_calls is None:
            return prior_output_from_toolcall, tool_call_messages

        for tool_call in tool_calls:
            # Kiln "task_response" tool is used for returning structured output via tool calls. Load the output from the tool call.
            if tool_call.function.name == "task_response":
                prior_output_from_toolcall = tool_call.function.arguments
                continue

            # Process normal tool calls (not the "task_response" tool)
            tool_name = tool_call.function.name
            tool = next(
                (
                    tool
                    for tool in self.cached_available_tools()
                    if tool.name() == tool_name
                ),
                None,
            )
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
                json_schema = json.dumps(
                    tool.toolcall_definition()["function"]["parameters"]
                )
                validate_schema_with_value_error(parsed_args, json_schema)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to validate arguments for tool '{tool_name}'. The arguments didn't match the tool's schema. The arguments were: {parsed_args}\n The error was: {e}"
                ) from e

            result = tool.run(**parsed_args)

            tool_call_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    # TODO: check if this really needs to be a string. If it does, run should be forced to return a string and we should avoid the str()
                    "content": str(result),
                }
            )

        if prior_output_from_toolcall is not None and len(tool_call_messages) > 0:
            raise RuntimeError(
                "task_response tool call and normal tool call results were both provided in the same turn. This is not supported as we should both return tool call results to the model, and end the turn. Switching to structured output mode other than tools will make this error impossible."
            )

        return prior_output_from_toolcall, tool_call_messages
