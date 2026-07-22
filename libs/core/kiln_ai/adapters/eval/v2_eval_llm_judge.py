"""V2 adapter for LLM Judge evaluations.

Supports two scoring modes:
- LLM-as-Judge (g_eval=False): uses structured output directly.
- G-Eval (g_eval=True): uses logprob-weighted scoring.

The prompt_template is rendered with Jinja2 using the EvalTaskInput fields
as the template namespace.
"""

from typing import TYPE_CHECKING

from jinja2 import UndefinedError

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.eval.base_eval import (
    JUDGE_RATIONALE_KEY,
    REASONING_SCHEMA_KEY,
    BaseEval,
    BaseV2EvalBridge,
)

if TYPE_CHECKING:
    from kiln_ai.adapters.model_adapters.base_adapter import SkillsDict
    from kiln_ai.datamodel.task import RunConfigProperties

from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
    build_g_eval_score,
    build_llm_as_judge_score,
    g_eval_single_metric,
    metric_offsets,
    raw_output_from_logprobs,
    score_from_token_string,
)
from kiln_ai.adapters.ml_model_list import (
    ModelProviderName,
    built_in_models_from_provider,
    default_structured_output_mode_for_model_provider,
)
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel.eval import (
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


class _LlmJudgeTask(Task, parent_of={}):
    """Ephemeral Task for invoking an LLM judge via adapter_for_task().

    Creates a temporary Project/Task with the system prompt and output
    JSON schema.
    """

    def __init__(
        self,
        system_prompt: str,
        output_json_schema: str,
    ):
        tmp_project = Project(name="LlmJudge")
        super().__init__(
            name="LlmJudge Task",
            parent=tmp_project,
            instruction=system_prompt,
            output_json_schema=output_json_schema,
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

        namespace = eval_input.model_dump()
        try:
            rendered_prompt = _template_env.from_string(props.prompt_template).render(
                **namespace
            )
        except JinjaExtractionError as e:
            return V2EvalResult(
                skipped_reason=SkippedReason.extraction_failed,
                skipped_detail=f"Template rendering failed: {e}",
            )
        except UndefinedError as e:
            return V2EvalResult(
                skipped_reason=SkippedReason.missing_reference_key,
                skipped_detail=f"Template references missing data: {e}",
            )

        # Ask the judge to state WHY in the same structured response as the
        # scores. Without this the judge leaves no rationale behind: V2 runs a
        # single SIMPLE call (no chain-of-thought turn), so unless the provider
        # happens to return native reasoning content, EvalRun
        # intermediate_outputs is empty and no verdict can be audited.
        #
        # Not in g_eval mode: that path rebuilds raw JSON from logprobs and
        # requires each metric name to appear EXACTLY once in it, so a free-text
        # rationale that happens to quote a score name would turn a missing
        # rationale into a hard scoring failure. g_eval keeps native provider
        # reasoning only.
        reasoning_instruction = None if props.g_eval else props.thinking_instruction
        output_json_schema = BaseEval.build_score_schema(
            self.eval,
            allow_float_scores=False,
            reasoning_instruction=reasoning_instruction,
        )

        system_prompt = props.system_prompt or _DEFAULT_SYSTEM_PROMPT

        judge_task = _LlmJudgeTask(
            system_prompt=system_prompt,
            output_json_schema=output_json_schema,
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

        adapter = adapter_for_task(
            judge_task,
            run_config_properties=KilnAgentRunConfigProperties(
                model_name=model_name,
                model_provider_name=provider,
                prompt_id=PromptGenerators.SIMPLE,
                structured_output_mode=structured_output_mode,
            ),
            base_adapter_config=AdapterConfig(
                allow_saving=False,
                top_logprobs=top_logprobs,
            ),
        )

        _, run_output = await adapter.invoke_returning_run_output(rendered_prompt)

        # Lift the rationale out of the scored output. Both scoring paths derive
        # their metric list from output.keys(), so leaving it in would fail as
        # "No score found for metric: reasoning".
        judge_reasoning: str | None = None
        if reasoning_instruction and isinstance(run_output.output, dict):
            popped = run_output.output.pop(REASONING_SCHEMA_KEY, None)
            if isinstance(popped, str) and popped.strip():
                judge_reasoning = popped.strip()

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

        # Reasoning-capable providers already deposit native reasoning under the
        # same key. Keep both rather than clobbering either: the web UI reads
        # `reasoning` first, so whichever is present still surfaces.
        intermediate_outputs = dict(run_output.intermediate_outputs or {})
        if judge_reasoning:
            if intermediate_outputs.get(REASONING_SCHEMA_KEY):
                intermediate_outputs[JUDGE_RATIONALE_KEY] = judge_reasoning
            else:
                intermediate_outputs[REASONING_SCHEMA_KEY] = judge_reasoning

        return V2EvalResult(
            scores=scores,
            intermediate_outputs=intermediate_outputs or None,
        )
