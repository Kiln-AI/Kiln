"""Built-in LLM tools: ``llm`` and ``llm_judge``.

Both run entirely parent-side (the model call never happens in a sandbox
child). They share :func:`run_llm_call`, which is extracted from the non-g-eval
path of ``LlmJudgeEval.evaluate``.

Imports of the adapter/eval stack are function-local: ``tools`` importing the
adapter stack at module scope would cycle (``base_adapter`` imports
``tool_registry``). ``RunOutput`` comes from the standalone
``kiln_ai.adapters.run_output`` module (no cycle) so it can annotate the shared
helper's return type.
"""

import json

from jinja2 import TemplateSyntaxError, UndefinedError

from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel.json_schema import validate_schema_dict
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import KilnTool, ToolCallContext, ToolCallResult
from kiln_ai.utils.jinja_engine import JinjaExtractionError, _template_env

_DEFAULT_SYSTEM_PROMPT = (
    "Your job is to evaluate a model's performance on a task. "
    "Score the output according to the criteria provided."
)


async def run_llm_call(
    *,
    model: str,
    provider: str,
    system_prompt: str | None,
    rendered_prompt: str,
    output_json_schema: str | None,
) -> RunOutput:
    """Make a single parent-side model call and return its ``RunOutput``.

    Mirrors the machinery ``LlmJudgeEval`` uses for its non-g-eval path: an
    ephemeral judge Task invoked through ``adapter_for_task``.

    When ``output_json_schema`` is None the call is free-text and
    ``run_output.output`` is a ``str``; when set it is structured and
    ``run_output.output`` is a ``dict``.
    """
    # Function-local imports to avoid the tools -> adapter -> tool_registry cycle.
    from kiln_ai.adapters.adapter_registry import adapter_for_task
    from kiln_ai.adapters.ml_model_list import (
        ModelProviderName,
        default_structured_output_mode_for_model_provider,
    )
    from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
    from kiln_ai.datamodel.project import Project
    from kiln_ai.datamodel.prompt_id import PromptGenerators
    from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
    from kiln_ai.datamodel.task import StructuredOutputMode, Task

    if provider not in ModelProviderName.__members__:
        raise ValueError(f"Invalid model provider: {provider}")
    provider_enum = ModelProviderName(provider)

    tmp_project = Project(name="LlmTool")
    judge_task = Task(
        name="LlmTool Task",
        parent=tmp_project,
        instruction=system_prompt or _DEFAULT_SYSTEM_PROMPT,
        output_json_schema=output_json_schema,
    )

    structured_output_mode = default_structured_output_mode_for_model_provider(
        model,
        provider_enum,
        default=StructuredOutputMode.json_schema,
        disallowed_modes=[
            StructuredOutputMode.function_calling,
            StructuredOutputMode.function_calling_weak,
        ],
    )

    adapter = adapter_for_task(
        judge_task,
        run_config_properties=KilnAgentRunConfigProperties(
            model_name=model,
            model_provider_name=provider_enum,
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=structured_output_mode,
        ),
        base_adapter_config=AdapterConfig(
            allow_saving=False,
            top_logprobs=None,
        ),
    )

    _, run_output = await adapter.invoke_returning_run_output(rendered_prompt)
    return run_output


def _render_prompt(prompt: str, input_data: dict) -> str:
    """Render ``prompt`` as a Jinja2 template against ``input_data``.

    Jinja errors (missing variables, invalid extraction) surface as a raised
    ValueError, which the sandbox bridge maps to a tool call error.
    """
    try:
        return _template_env.from_string(prompt).render(**input_data)
    except TemplateSyntaxError as e:
        raise ValueError(
            f"Invalid prompt template: {e.message} (line {e.lineno})"
        ) from e
    except JinjaExtractionError as e:
        raise ValueError(f"Prompt template rendering failed: {e}") from e
    except UndefinedError as e:
        raise ValueError(f"Prompt template references missing data: {e}") from e


_LLM_TOOL_PARAMETERS_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "Jinja2 prompt template rendered against `input`.",
        },
        "model": {
            "type": "string",
            "description": "The model name to call.",
        },
        "provider": {
            "type": "string",
            "description": "The model provider name to call.",
        },
        "input": {
            "type": "object",
            "description": "Variables made available to the prompt template.",
        },
        "schema": {
            "type": "object",
            "description": "Optional JSON schema forcing structured output.",
        },
        "system_prompt": {
            "type": "string",
            "description": "Optional system prompt for the model call.",
        },
    },
    "required": ["prompt", "model", "provider"],
    "additionalProperties": False,
}


class LlmTool(KilnTool):
    """Make a model call from within a code judge or agent.

    Renders a Jinja2 prompt, optionally forces structured output via a JSON
    schema, and returns the model's response (free text, or a JSON string when a
    schema is supplied).
    """

    def __init__(self):
        super().__init__(
            tool_id=KilnBuiltInToolId.LLM,
            name="llm",
            description=(
                "Call a language model with a rendered prompt. Provide an optional "
                "JSON schema to force structured output."
            ),
            parameters_schema=_LLM_TOOL_PARAMETERS_SCHEMA,
        )

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        rendered_prompt = _render_prompt(kwargs["prompt"], kwargs.get("input") or {})

        schema = kwargs.get("schema")
        if schema is not None:
            validate_schema_dict(schema, require_object=True)
            output_json_schema = json.dumps(schema, ensure_ascii=False)
        else:
            output_json_schema = None

        run_output = await run_llm_call(
            model=kwargs["model"],
            provider=kwargs["provider"],
            system_prompt=kwargs.get("system_prompt"),
            rendered_prompt=rendered_prompt,
            output_json_schema=output_json_schema,
        )

        output = (
            run_output.output
            if isinstance(run_output.output, str)
            else json.dumps(run_output.output, ensure_ascii=False)
        )
        return ToolCallResult(output=output)


_LLM_JUDGE_TOOL_PARAMETERS_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "Jinja2 prompt template rendered against `input`.",
        },
        "model": {
            "type": "string",
            "description": "The model name to call.",
        },
        "provider": {
            "type": "string",
            "description": "The model provider name to call.",
        },
        "input": {
            "type": "object",
            "description": "Variables made available to the prompt template.",
        },
        "system_prompt": {
            "type": "string",
            "description": "Optional system prompt for the model call.",
        },
    },
    "required": ["prompt", "model", "provider"],
    "additionalProperties": False,
}


class LlmJudgeTool(KilnTool):
    """Run an LLM-as-judge scoring call using the enclosing code judge's schema.

    Only available inside a code judge, where the eval's score schema is provided
    via ``ToolCallContext.eval_output_schema``. Returns a JSON string mapping each
    metric to its float score.
    """

    def __init__(self):
        super().__init__(
            tool_id=KilnBuiltInToolId.LLM_JUDGE,
            name="llm_judge",
            description=(
                "Score an output with an LLM using the code judge's own scoring "
                "schema. Returns a JSON object of metric scores."
            ),
            parameters_schema=_LLM_JUDGE_TOOL_PARAMETERS_SCHEMA,
        )

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        if context is None or context.eval_output_schema is None:
            raise ValueError(
                "llm_judge is only available inside a code judge; use 'llm' with "
                "an explicit schema elsewhere."
            )

        # Function-local import to avoid the tools -> adapter -> tool_registry cycle.
        from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
            build_llm_as_judge_score,
            score_from_token_string,
        )

        rendered_prompt = _render_prompt(kwargs["prompt"], kwargs.get("input") or {})

        run_output = await run_llm_call(
            model=kwargs["model"],
            provider=kwargs["provider"],
            system_prompt=kwargs.get("system_prompt"),
            rendered_prompt=rendered_prompt,
            output_json_schema=context.eval_output_schema,
        )

        scores = build_llm_as_judge_score(run_output, score_from_token_string)
        return ToolCallResult(output=json.dumps(scores, ensure_ascii=False))
