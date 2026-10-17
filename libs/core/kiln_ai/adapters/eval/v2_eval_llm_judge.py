"""V2 adapter for LLM Judge evaluations.

Supports two scoring modes:
- LLM-as-Judge (g_eval=False): uses structured output directly.
- G-Eval (g_eval=True): uses logprob-weighted scoring.

With trace_toolset_version set, the judge also gets the trace tools: read-only
tools for reading the judged trace, at that locked toolset version. It can't be
combined with G-Eval. Such a judge answers in two turns: it reads the trace with
the tools and describes its decision, then gives its scores in a final turn that
alone carries the structured output format.

The prompt_template is rendered with Jinja2 using the EvalTaskInput fields
as the template namespace.
"""

import asyncio
from typing import TYPE_CHECKING, Any

import litellm
from jinja2 import Environment, UndefinedError, meta

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.eval.base_eval import (
    BaseEval,
    BaseV2EvalBridge,
    format_judge_instructions,
    validate_judge_thinking_level,
)

if TYPE_CHECKING:
    from kiln_ai.adapters.model_adapters.base_adapter import SkillsDict
    from kiln_ai.datamodel.task import RunConfigProperties

from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.eval.eval_utils.errors import JudgeContextExceededError
from kiln_ai.adapters.eval.eval_utils.eval_trace_formatter import EvalTraceFormatter
from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
    build_g_eval_score,
    build_llm_as_judge_score,
    g_eval_single_metric,
    metric_offsets,
    raw_output_from_logprobs,
    score_from_token_string,
)
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import check_reference_key
from kiln_ai.adapters.eval.trace_tools import (
    UnsupportedTraceToolsetVersion,
    judge_template_env,
    trace_toolset,
)
from kiln_ai.adapters.ml_model_list import (
    ModelProviderName,
    built_in_models_from_provider,
    default_structured_output_mode_for_model_provider,
)
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.retry_classification import unwrap_kiln_run_error
from kiln_ai.datamodel.eval import (
    TRACE_OVERVIEW_VERSION_WITHOUT_TOOLS,
    EvalConfig,
    EvalTaskInput,
    LlmJudgeProperties,
    SkippedReason,
    V2EvalResult,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import StructuredOutputMode, Task
from kiln_ai.utils.jinja_engine import JinjaExtractionError, _template_env

_DEFAULT_SYSTEM_PROMPT = (
    "Your job is to evaluate a model's performance on a task. "
    "Score the output according to the criteria provided."
)


def system_prompt_from_trace(trace: list[dict[str, Any]] | None) -> str:
    """The system prompt the evaluated model was given: the first system
    message in its trace, or an empty string when there is none."""
    for message in trace or []:
        if message.get("role") == "system":
            # Loose dicts are the runtime reality for traces; the formatter reads
            # them like its typed message params.
            return EvalTraceFormatter.content_from_message(message) or ""  # type: ignore[arg-type]
    return ""


def _render_prompt(env: Environment, template: str, namespace: dict[str, Any]) -> str:
    return env.from_string(template).render(**namespace)


def _unknown_template_variables(template: str, namespace: dict[str, Any]) -> set[str]:
    """Top-level variables the template uses that aren't EvalTaskInput fields.

    Distinguishes a template-authoring bug (typo'd variable name) from
    genuinely missing data (e.g. an absent reference_data key) when rendering
    raises UndefinedError.
    """
    ast = _template_env.parse(template)
    return meta.find_undeclared_variables(ast) - set(namespace)


def _judge_intermediate_outputs(
    intermediate_outputs: dict[str, str] | None, trace_tools_on: bool
) -> dict[str, str] | None:
    """The intermediate outputs a judgment reports.

    A trace tools judge's reasoning is its first-turn findings, reported as
    ``chain_of_thought``. Its final turn only formats the scores, so that turn's own
    ``reasoning`` is left out here; it stays in the judge trace.
    """
    if not trace_tools_on or intermediate_outputs is None:
        return intermediate_outputs
    return {
        key: value for key, value in intermediate_outputs.items() if key != "reasoning"
    }


class _LlmJudgeTask(Task, parent_of={}):
    """Ephemeral Task for invoking an LLM judge via adapter_for_task().

    Creates a temporary Project/Task with the system prompt, output JSON
    schema and, for a judge that thinks in a turn of its own, the thinking
    instruction.
    """

    def __init__(
        self,
        system_prompt: str,
        output_json_schema: str,
        thinking_instruction: str | None = None,
    ):
        tmp_project = Project(name="LlmJudge")
        super().__init__(
            name="LlmJudge Task",
            parent=tmp_project,
            instruction=system_prompt,
            output_json_schema=output_json_schema,
            thinking_instruction=thinking_instruction,
        )


class LlmJudgeEval(BaseV2EvalBridge):
    """V2 adapter that invokes an LLM to score eval inputs.

    Uses LlmJudgeProperties from the eval config to configure the judge:
    model, prompt template, scoring mode, etc.
    """

    def __init__(
        self,
        eval_config: EvalConfig,
        run_config: "RunConfigProperties | None" = None,
        skills: "SkillsDict | None" = None,
    ) -> None:
        super().__init__(eval_config, run_config, skills)
        if not isinstance(self.properties, LlmJudgeProperties):
            raise ValueError(
                "LlmJudgeEval requires LlmJudgeProperties in the eval config"
            )
        if self.properties.model_provider not in ModelProviderName.__members__:
            raise ValueError(
                f"Invalid model provider: {self.properties.model_provider}"
            )

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        props = self.properties
        assert isinstance(props, LlmJudgeProperties)

        # Before the render and before any model call: a judge that declares a
        # reference key it cannot get must skip loudly, not score blind. A template can
        # be permissive (a hand-written one may guard its own lookups), so this declared
        # requirement is what refuses missing ground truth. It also runs first for the
        # backend-baked default, whose `<reference_answer>` block is unconditional —
        # that one would raise below and land on the same skip, one step later.
        #
        # Unlike the runner's early skips, this one cannot be hoisted ahead of trace
        # generation (`eval_runner.py` run_job): the requirement is a property of this
        # judge's config, and the runner scores one item against many judges. Reading it
        # there would put per-type properties back in the runner, which is exactly what
        # the `evaluate()` contract exists to keep out.
        for reference_key in props.reference_keys:
            _, skip_reason, skip_detail = check_reference_key(reference_key, eval_input)
            if skip_reason is not None:
                return V2EvalResult(
                    skipped_reason=skip_reason,
                    skipped_detail=skip_detail,
                )

        trace_tools_version = props.trace_toolset_version
        trace_tools_on = trace_tools_version is not None
        if trace_tools_on and not eval_input.trace:
            return V2EvalResult(
                skipped_reason=SkippedReason.missing_trace,
                skipped_detail=(
                    "This judge reads the trace with trace tools, but this run has "
                    "no trace."
                ),
            )
        try:
            toolset = trace_toolset(
                trace_tools_version
                if trace_tools_version is not None
                else TRACE_OVERVIEW_VERSION_WITHOUT_TOOLS
            )
        except UnsupportedTraceToolsetVersion as e:
            return V2EvalResult(
                skipped_reason=SkippedReason.type_not_available,
                skipped_detail=(
                    f"This judge uses trace tools version {e.version}, which this "
                    "version of Kiln doesn't support. Update Kiln to run it."
                ),
            )

        namespace = eval_input.model_dump()
        # Always bound (even when unset) so templates referencing it never hit
        # StrictUndefined; blank steps render as an empty <steps> body.
        namespace["judge_instructions"] = format_judge_instructions(
            props.judge_instructions
        )
        # Bound for hand-written templates that judge a single turn's
        # final_message against the system prompt without the full trace, and
        # for the default trace tools prompt.
        namespace["system_prompt"] = system_prompt_from_trace(eval_input.trace)

        # Parsing a large trace is CPU-bound, so the view is built and the
        # template rendered off the event loop. A judge with trace tools off that
        # uses trace_overview builds its view during the render.
        trace_view = (
            await asyncio.to_thread(toolset.build_view, namespace["trace"])
            if trace_tools_on
            else None
        )
        template_env = judge_template_env(toolset, namespace["trace"], trace_view)
        try:
            rendered_prompt = await asyncio.to_thread(
                _render_prompt, template_env, props.prompt_template, namespace
            )
        except JinjaExtractionError as e:
            return V2EvalResult(
                skipped_reason=SkippedReason.extraction_failed,
                skipped_detail=f"Template rendering failed: {e}",
            )
        except UndefinedError as e:
            # A typo'd template variable and genuinely missing reference data
            # both raise UndefinedError; only the latter is a data problem.
            unknown = _unknown_template_variables(props.prompt_template, namespace)
            if unknown:
                return V2EvalResult(
                    skipped_reason=SkippedReason.extraction_failed,
                    skipped_detail=(
                        "Template references unknown variable(s): "
                        + ", ".join(sorted(unknown))
                    ),
                )
            return V2EvalResult(
                skipped_reason=SkippedReason.missing_reference_key,
                skipped_detail=f"Template references missing data: {e}",
            )

        output_json_schema = BaseEval.build_score_schema(
            self.eval, allow_float_scores=False
        )

        system_prompt = props.system_prompt or _DEFAULT_SYSTEM_PROMPT

        judge_task = _LlmJudgeTask(
            system_prompt=system_prompt,
            output_json_schema=output_json_schema,
            thinking_instruction=toolset.judge_thinking_instruction
            if trace_tools_on
            else None,
        )

        model_name = props.model_name
        provider = ModelProviderName(props.model_provider)

        if props.g_eval:
            model_provider = built_in_models_from_provider(provider, model_name)
            if model_provider is not None and not model_provider.supports_logprobs:
                raise ValueError(
                    f"g_eval=True requires logprobs support, but provider "
                    f"'{props.model_provider}' for model '{model_name}' does not "
                    f"support logprobs"
                )

        structured_output_mode = default_structured_output_mode_for_model_provider(
            model_name,
            provider,
            default=StructuredOutputMode.json_schema,
            disallowed_modes=[
                StructuredOutputMode.function_calling,
                StructuredOutputMode.function_calling_weak,
            ],
        )

        top_logprobs = 10 if props.g_eval else None

        # Pass only the fields the judge's run_config sets. An unset field keeps its
        # default: the adapter reads an unset thinking_level as "use the provider's
        # default", which keeps older configs unchanged. Passing fields to the
        # constructor (not model_copy) validates them and marks them as set.
        overrides = (
            props.run_config.model_dump(exclude_none=True)
            if props.run_config is not None
            else {}
        )
        if "thinking_level" in overrides:
            validate_judge_thinking_level(
                model_name, props.model_provider, overrides["thinking_level"]
            )
        run_config_properties = KilnAgentRunConfigProperties(
            model_name=model_name,
            model_provider_name=provider,
            prompt_id=PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT
            if trace_tools_on
            else PromptGenerators.SIMPLE,
            structured_output_mode=structured_output_mode,
            **overrides,
        )

        adapter = adapter_for_task(
            judge_task,
            run_config_properties=run_config_properties,
            base_adapter_config=AdapterConfig(
                allow_saving=False,
                top_logprobs=top_logprobs,
                unmanaged_tools=toolset.build_tools(trace_view)
                if trace_view is not None
                else None,
                # A trace tool loop resends a growing prefix on every round.
                automatic_prompt_caching=trace_tools_on,
                # Models asked to read with tools and answer in the score format in one
                # turn tend to wrap the JSON in prose.
                separate_final_answer_turn=trace_tools_on,
            ),
        )

        try:
            judge_run, run_output = await adapter.invoke_returning_run_output(
                rendered_prompt
            )
        except KilnRunError as e:
            if isinstance(unwrap_kiln_run_error(e), litellm.ContextWindowExceededError):
                raise JudgeContextExceededError.from_run_error(e) from e
            raise

        if props.g_eval:
            scores = build_g_eval_score(
                run_output,
                raw_output_from_logprobs,
                metric_offsets,
                g_eval_single_metric,
            )
        else:
            scores = build_llm_as_judge_score(
                run_output,
                score_from_token_string,
            )

        return V2EvalResult(
            scores=scores,
            intermediate_outputs=_judge_intermediate_outputs(
                run_output.intermediate_outputs, trace_tools_on
            ),
            # `usage`, not `cumulative_usage`: it already accumulates every call this
            # judgment made, and it is the one that carries latency.
            usage=judge_run.usage,
            judge_trace=judge_run.trace,
        )
