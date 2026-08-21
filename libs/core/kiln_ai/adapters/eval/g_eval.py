from typing import Dict, List, Tuple

from litellm.types.utils import ChatCompletionTokenLogprob

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.eval_utils.eval_trace_formatter import EvalTraceFormatter
from kiln_ai.adapters.eval.eval_utils.eval_utils import EvalUtils
from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
    g_eval_single_metric as _g_eval_single_metric,
)
from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
    metric_offsets as _metric_offsets,
)
from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
    rating_token_to_score as _rating_token_to_score,
)
from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
    raw_output_from_logprobs as _raw_output_from_logprobs,
)
from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
    score_from_token_string as _score_from_token_string,
)
from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
    token_search_range as _token_search_range,
)
from kiln_ai.adapters.ml_model_list import (
    default_structured_output_mode_for_model_provider,
)
from kiln_ai.adapters.model_adapters.base_adapter import (
    AdapterConfig,
    RunOutput,
    SkillsDict,
)
from kiln_ai.adapters.prompt_builders import PromptGenerators
from kiln_ai.datamodel import Project, Task, TaskRun
from kiln_ai.datamodel.eval import EvalConfig, EvalConfigType, EvalDataType, EvalScores
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import RunConfigProperties, StructuredOutputMode


class GEvalTask(Task, parent_of={}):
    """
    Kiln task for executing a G-Eval. Can be run on any Kiln adapter which supports logprobs.

    Note G-Eval implements both G-Eval and LLM as Judge as they are very similar.
    """

    def __init__(self, eval_config: EvalConfig):
        tmp_project = Project(name="GEval")

        # Build a simple LLM as Judge system instruction
        system_instruction = "Your job to evaluate a model's performance on a task. Blocks will be marked with <eval_data> tags.\n"
        # Optionally add a short task description
        task_description = eval_config.properties.get("task_description", None)
        if task_description:
            system_instruction += f"\nThe task the model was given is as follows:\n<eval_data>\n<task_description>{task_description}</task_description>\n</eval_data>\n"

        # Build the COT eval instructions
        steps = eval_config.properties.get("eval_steps", [])
        if not isinstance(steps, list):
            raise ValueError("eval_steps must be a list.")
        if len(steps) == 1:
            cot_instructions = "First, think step by step about the model's performance following this evaluation step:\n\n"
            cot_instructions += f"{steps[0]}\n"
        else:
            cot_instructions = "First, think step by step about the model's performance following these evaluation steps:\n\n"
            for i, step in enumerate(steps):
                cot_instructions += f"{i + 1}) {step}\n"

        eval = eval_config.parent_eval()
        if not eval:
            raise ValueError("Eval config must have a parent eval")

        # Build the output schema from the eval's target output scores.
        # We restrict the LLM's output scoring schema to discrete scores (pass/fail/critical/1-5) - allow_float_scores=False
        # However, the final scores from the evaluator can be a float (see later logprob calculation, which requires discrete token outputs)
        output_schema = BaseEval.build_score_schema(eval, allow_float_scores=False)

        super().__init__(
            name="GEval Task",
            parent=tmp_project,
            instruction=system_instruction,
            thinking_instruction=cot_instructions,
            output_json_schema=output_schema,
        )


class GEval(BaseEval):
    """
    A evaluator which implements G-Eval and LLM as Judge.

    G-Eval is a method of evaluating the quality of a model's output. It is a weighted average of the scores of the tokens in the output. The weights are the log probabilities of the tokens in the output. https://arxiv.org/abs/2303.16634

    LLM as Judge is a method of evaluating the quality of a model's output. It simply asks the LLM to score, and uses the returned output (no logprobs needed). Also called direct evaluation.

    @misc{liu2023gevalnlgevaluationusing,
        title={G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment},
        author={Yang Liu and Dan Iter and Yichong Xu and Shuohang Wang and Ruochen Xu and Chenguang Zhu},
        year={2023},
        eprint={2303.16634},
        archivePrefix={arXiv},
        primaryClass={cs.CL},
        url={https://arxiv.org/abs/2303.16634},
    }
    """

    def __init__(
        self,
        eval_config: EvalConfig,
        run_config: RunConfigProperties | None,
        skills: SkillsDict | None = None,
    ):
        if (
            eval_config.config_type != EvalConfigType.g_eval
            and eval_config.config_type != EvalConfigType.llm_as_judge
        ):
            raise ValueError(
                f"GEval must be initialized with a GEval or LLM as Judge config_type. Got {eval_config.config_type}"
            )

        super().__init__(eval_config, run_config, skills=skills)

        self.geval_task = GEvalTask(eval_config)

    def generate_final_answer_run_description(
        self, eval_input: str, eval_output: str
    ) -> str:
        return f"""The model was given the following input for the task: 
<eval_data>
{eval_input}
</eval_data>

The model produced the following output for the task:
<eval_data>
{eval_output}
</eval_data>
"""

    def generate_ref_ans_run_description(
        self, eval_input: str, eval_output: str, reference_answer: str
    ) -> str:
        return f"""The model was given the following input for the task: 
<eval_data>
{eval_input}
</eval_data>

The model produced the following output for the task:
<eval_data>
{eval_output}
</eval_data>

This is the reference answer:
<eval_data>
{reference_answer}
</eval_data>
"""

    def generate_full_trace_run_description(
        self,
        eval_input: str,
        available_tools: str | None,
        conversation_history: str,
    ) -> str:
        description = ""
        description += f"""The model was given the following <user_input> for the <task_description>: 
<eval_data>
<user_input>{eval_input}</user_input>
</eval_data>
"""
        # Get properties from spec if available, otherwise from eval.template_properties (for legacy evals)
        spec = self.eval.associated_spec(readonly=True)

        # Spec uses different keys than legacy eval template_properties
        if spec:
            # Spec: tool_use_guidelines, appropriate_tool_use_examples, inappropriate_tool_use_examples
            tool_use_guidelines = str(spec.properties.get("tool_use_guidelines") or "")
            appropriate_tool_use_examples = str(
                spec.properties.get("appropriate_tool_use_examples") or ""
            )
            inappropriate_tool_use_examples = str(
                spec.properties.get("inappropriate_tool_use_examples") or ""
            )
            description += f"""The model was given the following <tool_use_guidelines>:
<eval_data>
<tool_use_guidelines>
{tool_use_guidelines}
</tool_use_guidelines>
</eval_data>
"""
            description += f"""The model was given the following <appropriate_tool_use_examples>:
<eval_data>
<appropriate_tool_use_examples>
{appropriate_tool_use_examples}
</appropriate_tool_use_examples>
</eval_data>
"""
            description += f"""The model was given the following <inappropriate_tool_use_examples>:
<eval_data>
<inappropriate_tool_use_examples>
{inappropriate_tool_use_examples}
</inappropriate_tool_use_examples>
</eval_data>
"""
        elif self.eval.template_properties:
            # Legacy eval: appropriate_tool_use_guidelines, inappropriate_tool_use_guidelines
            appropriate_tool_use_guidelines = str(
                self.eval.template_properties.get("appropriate_tool_use_guidelines")
                or ""
            )
            inappropriate_tool_use_guidelines = str(
                self.eval.template_properties.get("inappropriate_tool_use_guidelines")
                or ""
            )

            description += f"""The model was given the following <appropriate_tool_use_guidelines> guidelines: 
<eval_data>
<appropriate_tool_use_guidelines>
{appropriate_tool_use_guidelines}
</appropriate_tool_use_guidelines>
</eval_data>
"""
            # Only include if it has content since it is optional
            if inappropriate_tool_use_guidelines:
                description += f"""The model was given the following <inappropriate_tool_use_guidelines> guidelines: 
<eval_data>
<inappropriate_tool_use_guidelines>
{inappropriate_tool_use_guidelines}
</inappropriate_tool_use_guidelines>
</eval_data>
"""

        if available_tools is not None:
            if available_tools != "":
                description += f"""
This is the list of tools available to the model:
<eval_data>
<available_tools>{available_tools}</available_tools>
</eval_data>
"""
            else:
                description += """
There were no tools available to the model.
"""

        description += f"""
This is the full conversation history for the task run:
<eval_data>
<conversation_history>{conversation_history}</conversation_history>
</eval_data>
"""
        return description

    async def run_eval(
        self, task_run: TaskRun, eval_job_item: TaskRun | None = None
    ) -> tuple[EvalScores, Dict[str, str] | None]:
        """
        Run this eval on the given task run.
        """

        model_name, provider = self.model_and_provider()

        # Only fetch logprobs for G-Eval
        # There are at most 5 valid rating tokens per rating type (five_star being largest), so 10 is more than enough to get to the very very unlikely
        top_logprobs = (
            10 if self.eval_config.config_type == EvalConfigType.g_eval else None
        )

        # We don't expose setting this manually in the UI, so pull a recommended mode from ml_model_list
        structured_output_mode = default_structured_output_mode_for_model_provider(
            model_name,
            provider,
            default=StructuredOutputMode.json_schema,
            # G-eval expects JSON, so don't allow function calling modes
            disallowed_modes=[
                StructuredOutputMode.function_calling,
                StructuredOutputMode.function_calling_weak,
            ],
        )

        adapter = adapter_for_task(
            self.geval_task,
            run_config_properties=KilnAgentRunConfigProperties(
                model_name=model_name,
                model_provider_name=provider,
                # We always use Simple COT for G-Eval and LLM as Judge
                prompt_id=PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT,
                structured_output_mode=structured_output_mode,
            ),
            base_adapter_config=AdapterConfig(
                # Don't save this run into the task_runs. It will be saved into an eval_run where it belongs
                allow_saving=False,
                top_logprobs=top_logprobs,
            ),
        )

        if self.eval.evaluation_data_type == EvalDataType.full_trace:
            if task_run.trace is None:
                raise ValueError("Task run trace is required for full trace evaluation")

            available_tools = await EvalUtils.formatted_available_tools_from_task_run(
                task_run
            )
            run_description = self.generate_full_trace_run_description(
                task_run.input,
                available_tools,
                EvalTraceFormatter.trace_to_formatted_conversation_history(
                    task_run.trace
                ),
            )

        elif self.eval.evaluation_data_type == EvalDataType.reference_answer:
            if eval_job_item is None:
                raise ValueError(
                    "Eval job item is required for reference answer evaluation"
                )
            run_description = self.generate_ref_ans_run_description(
                task_run.input, task_run.output.output, eval_job_item.output.output
            )

        else:  # EvalDataType.final_answer
            run_description = self.generate_final_answer_run_description(
                task_run.input, task_run.output.output
            )

        # We don't need the run, but invoke_returning_run_output() runs validations for us over _run()
        _, run_output = await adapter.invoke_returning_run_output(run_description)

        if self.eval_config.config_type == EvalConfigType.llm_as_judge:
            return self.build_llm_as_judge_score(
                run_output
            ), run_output.intermediate_outputs
        else:
            return self.build_g_eval_score(run_output), run_output.intermediate_outputs

    def build_llm_as_judge_score(self, run_output: RunOutput) -> EvalScores:
        """Build the LLM as Judge score for the given run and run output."""
        from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
            build_llm_as_judge_score,
        )

        return build_llm_as_judge_score(run_output, self.score_from_token_string)

    def build_g_eval_score(self, run_output: RunOutput) -> EvalScores:
        """Build the G-Eval score for the given run and run output.

        We create a weighted average of each rating using the logprobs.

        @misc{liu2023gevalnlgevaluationusing,
            title={G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment},
            author={Yang Liu and Dan Iter and Yichong Xu and Shuohang Wang and Ruochen Xu and Chenguang Zhu},
            year={2023},
            eprint={2303.16634},
            archivePrefix={arXiv},
            primaryClass={cs.CL},
            url={https://arxiv.org/abs/2303.16634},
        }
        """
        from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
            build_g_eval_score,
        )

        return build_g_eval_score(
            run_output,
            self.raw_output_from_logprobs,
            self.metric_offsets,
            self.g_eval_single_metric,
        )

    def g_eval_single_metric(
        self,
        run_output: RunOutput,
        metric: str,
        metric_offsets: Dict[str, int],
        raw_output: str,
    ) -> float | None:
        return _g_eval_single_metric(run_output, metric, metric_offsets, raw_output)

    def raw_output_from_logprobs(self, run_output: RunOutput) -> str:
        return _raw_output_from_logprobs(run_output)

    def token_search_range(
        self, raw_output: str, metric: str, metric_offsets: Dict[str, int]
    ) -> Tuple[int, int]:
        return _token_search_range(raw_output, metric, metric_offsets)

    def rating_token_to_score(
        self, token_logprob: ChatCompletionTokenLogprob
    ) -> float | None:
        return _rating_token_to_score(token_logprob)

    def score_from_token_string(self, token: str) -> float | None:
        return _score_from_token_string(token)

    def metric_offsets(self, raw_output: str, metrics: List[str]) -> Dict[str, int]:
        return _metric_offsets(raw_output, metrics)
