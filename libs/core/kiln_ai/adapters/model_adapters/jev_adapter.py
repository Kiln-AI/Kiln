"""Adapter for TypeSafe AI's Jev models, which answer typed questions instead of
generating text.

Only `adapter_name` and `_run` are implemented: input validation, input transforms,
output parsing, output schema validation, run generation and error wrapping all come from
`BaseAdapter`. So a mapping bug shows up as the usual output-schema validation error
rather than a saved bad run.
"""

import json
import time
from typing import Any, Tuple

from kiln_ai.adapters.chat.chat_formatter import format_user_message
from kiln_ai.adapters.jev import JevClient
from kiln_ai.adapters.jev.jev_jsonschema import (
    ROOT_KEY,
    IncompatibleSchemaError,
    JevResult2JsonSchema,
    JSONSchema2Jev,
    UnexpectedAnswerError,
)
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.adapters.provider_tools import check_provider_warnings
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel import Task, Usage
from kiln_ai.datamodel.datamodel_enums import InputType, ModelProviderName
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    as_kiln_agent_run_config,
)
from kiln_ai.datamodel.tool_id import SKILL_TOOL_ID_PREFIX
from kiln_ai.utils.config import Config
from kiln_ai.utils.open_ai_types import (
    ChatCompletionAssistantMessageParamWrapper,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from kiln_ai.utils.usage import MessageUsage

JEV_ADAPTER_NAME = "kiln_jev_adapter"

ERROR_PREFIX = "Jev (TypeSafe AI) can't run this task:"

SUPPORTED_SHAPES = (
    "Supported property shapes: a string enum, an integer enum, a boolean, an integer "
    "with minimum and maximum spanning 2 to 10 values, or a number with minimum 0 and "
    "maximum 1."
)

PROBABILITY_DECIMAL_PLACES = 4


def build_jev_state(system_prompt: str, input: InputType) -> dict[str, Any]:
    """Build the `state` every question is asked against.

    An object rather than a string so the input keeps its structure and its relationship
    to the instructions stays explicit. The system prompt lives here instead of in each
    question because state is shared across questions.
    """
    return {"task_instructions": system_prompt, "input": input}


class JevAdapter(BaseAdapter):
    def __init__(
        self,
        kiln_task: Task,
        run_config: KilnAgentRunConfigProperties,
        base_adapter_config: AdapterConfig | None = None,
        client: JevClient | None = None,
    ) -> None:
        if not isinstance(run_config, KilnAgentRunConfigProperties):
            raise ValueError("JevAdapter requires KilnAgentRunConfigProperties")
        self._client = client
        super().__init__(
            task=kiln_task, run_config=run_config, config=base_adapter_config
        )

    def adapter_name(self) -> str:
        return JEV_ADAPTER_NAME

    async def _run(
        self,
        input: InputType,
        trace_ref: list[ChatCompletionMessageParam],
        prior_trace: list[ChatCompletionMessageParam] | None = None,
    ) -> Tuple[RunOutput, Usage | None]:
        self._reject_incompatible_run(prior_trace)

        schema = self.task.output_schema()
        if schema is None:
            raise ValueError(
                f"{ERROR_PREFIX} Jev only supports tasks with a structured output "
                "schema. Add an output JSON schema whose properties are enums, booleans, "
                "bounded integers, or numbers from 0 to 1."
            )
        try:
            question_set = JSONSchema2Jev().convert(schema)
        except IncompatibleSchemaError as err:
            raise _incompatible_schema_error(err) from err

        system_prompt = self._system_prompt()
        state = build_jev_state(system_prompt, input)

        client = self._client or _client_from_config()
        model_id = self.model_provider().model_id
        if model_id is None:
            raise ValueError(
                f"{ERROR_PREFIX} the selected model has no TypeSafe AI model ID."
            )

        call_started_at = time.perf_counter()
        response = await client.system_one(
            question_set.request(state=state, model=model_id)
        )
        latency_ms = int((time.perf_counter() - call_started_at) * 1000)

        try:
            decoded = JevResult2JsonSchema().convert(question_set, response.answers)
        except UnexpectedAnswerError as err:
            raise RuntimeError(
                f"TypeSafe AI returned an unexpected response: {err}"
            ) from err

        message_usage = MessageUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=_total_tokens(
                response.usage.input_tokens, response.usage.output_tokens
            ),
        )
        # Shaped like the LiteLLM adapter's trace so MessageUsage.from_trace sums it and
        # the run details, full-trace evals and error-with-trace UI all behave as usual.
        trace_ref[:] = [
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(
                role="user", content=format_user_message(input)
            ),
            ChatCompletionAssistantMessageParamWrapper(
                role="assistant",
                content=json.dumps(decoded.output, ensure_ascii=False),
                usage=message_usage,
            ),
        ]

        usage = Usage(
            input_tokens=message_usage.input_tokens,
            output_tokens=message_usage.output_tokens,
            total_tokens=message_usage.total_tokens,
            total_llm_latency_ms=latency_ms,
        )

        return (
            RunOutput(
                output=decoded.output,
                intermediate_outputs={
                    "jev_probabilities": json.dumps(
                        _rounded_probabilities(decoded.probabilities),
                        ensure_ascii=False,
                    ),
                    "jev_confidence": json.dumps(
                        decoded.confidence, ensure_ascii=False
                    ),
                },
                trace=trace_ref,
            ),
            usage,
        )

    def _reject_incompatible_run(
        self, prior_trace: list[ChatCompletionMessageParam] | None
    ) -> None:
        if prior_trace:
            raise ValueError(f"{ERROR_PREFIX} Jev only supports single-turn runs.")

        tools_config = as_kiln_agent_run_config(self.run_config).tools_config
        tool_ids = (tools_config.tools if tools_config is not None else None) or []
        skill_ids = [
            tool_id for tool_id in tool_ids if tool_id.startswith(SKILL_TOOL_ID_PREFIX)
        ]
        other_tool_ids = [
            tool_id
            for tool_id in tool_ids
            if not tool_id.startswith(SKILL_TOOL_ID_PREFIX)
        ]

        if other_tool_ids or self.base_adapter_config.unmanaged_tools:
            raise ValueError(
                f"{ERROR_PREFIX} Jev does not support tools. Remove tools from the run "
                "config."
            )
        # Skills reach the model as a callable tool ("load it with skill(name)"), which
        # Jev has no way to invoke, so a skill is as incompatible as any other tool.
        if skill_ids:
            raise ValueError(
                f"{ERROR_PREFIX} Jev does not support skills, which the model loads "
                "through a tool call. Remove the skills from the run config."
            )

    def _system_prompt(self) -> str:
        if self.prompt_builder is None:
            raise ValueError("JevAdapter requires a kiln_agent run config")
        # Jev never sees JSON formatting instructions: the output shape is carried by the
        # questions. Skills never reach here either, as a run config carrying one is
        # rejected above.
        prompt = self.prompt_builder.build_prompt(include_json_instructions=False)

        # Jev has no reasoning step, but thinking instructions are content, not just a
        # procedure: a legacy LLM-as-Judge config carries its eval steps there and
        # nowhere else, so dropping them would make every judge config on an eval the
        # same judge. Composed exactly as build_prompt_for_ui does, so Kiln's prompt
        # viewer and what Jev receives are the same text.
        thinking_instructions = self.prompt_builder.chain_of_thought_prompt()
        if thinking_instructions:
            prompt += "\n\n# Thinking Instructions\n\n" + thinking_instructions
        return prompt


def _client_from_config() -> JevClient:
    # A user-registry model resolves before kiln_model_provider_from reaches the provider
    # key check, so this is the only place that check runs for such a model.
    check_provider_warnings(ModelProviderName.typesafe)
    return JevClient(api_key=Config.shared().typesafe_api_key)


def _incompatible_schema_error(err: IncompatibleSchemaError) -> ValueError:
    if len(err.failures) == 1 and err.failures[0].key == ROOT_KEY:
        return ValueError(f"{ERROR_PREFIX} the output {err.failures[0].reason}.")
    details = "\n".join(f"- {f.key}: {f.reason}" for f in err.failures)
    return ValueError(
        f"{ERROR_PREFIX} the output schema has properties Jev can't answer:\n"
        f"{details}\n{SUPPORTED_SHAPES}"
    )


def _total_tokens(input_tokens: int | None, output_tokens: int | None) -> int | None:
    if input_tokens is None and output_tokens is None:
        return None
    return (input_tokens or 0) + (output_tokens or 0)


def _rounded_probabilities(
    probabilities: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    return {
        key: {
            value: round(probability, PROBABILITY_DECIMAL_PLACES)
            for value, probability in distribution.items()
        }
        for key, distribution in probabilities.items()
    }
