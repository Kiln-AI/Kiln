import math
from typing import Dict, List, Tuple

from litellm.types.utils import ChatCompletionTokenLogprob

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, RunOutput
from kiln_ai.adapters.prompt_builders import PromptGenerators
from kiln_ai.datamodel import Project, Task, TaskRun
from kiln_ai.datamodel.eval import EvalConfig, EvalConfigType, EvalScores
from kiln_ai.datamodel.task import RunConfig

# all the tokens we score for, and their float scores.
TOKEN_TO_SCORE_MAP: Dict[str, float] = {
    "1": 1.0,
    "2": 2.0,
    "3": 3.0,
    "4": 4.0,
    "5": 5.0,
    "pass": 1.0,
    "fail": 0.0,
    "critical": -1.0,
}


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
            system_instruction += f"\nThe task the model was given is as follows:\n<eval_data>\n{task_description}\n</eval_data>\n"

        # Build the COT eval instructions
        cot_instructions = "First, think step by step about the model's performance following these evaluation steps:\n\n"
        steps = eval_config.properties.get("eval_steps", None)
        if not steps or not isinstance(steps, list):
            raise ValueError("eval_steps must be a list")
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

    def __init__(self, eval_config: EvalConfig, run_config: RunConfig | None):
        if (
            eval_config.config_type != EvalConfigType.g_eval
            and eval_config.config_type != EvalConfigType.llm_as_judge
        ):
            raise ValueError(
                f"GEval must be initialized with a GEval or LLM as Judge config_type. Got {eval_config.config_type}"
            )

        super().__init__(eval_config, run_config)

        self.geval_task = GEvalTask(eval_config)

    async def run_eval(
        self, task_run: TaskRun
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

        adapter = adapter_for_task(
            self.geval_task,
            model_name,
            provider,
            # We always use Simple COT for G-Eval and LLM as Judge
            prompt_id=PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT,
            base_adapter_config=AdapterConfig(
                # Don't save this run into the task_runs. It will be saved into an eval_run where it belongs
                allow_saving=False,
                top_logprobs=top_logprobs,
            ),
        )

        input = f"""The model was given the following input for the task: 
<eval_data>
{task_run.input}
</eval_data>

The model produced the following output for the task:
<eval_data>
{task_run.output}
</eval_data>
"""

        # We don't need the run, but invoke_returning_run_output() runs validations for us over _run()
        _, run_output = await adapter.invoke_returning_run_output(input)

        if self.eval_config.config_type == EvalConfigType.llm_as_judge:
            return self.build_llm_as_judge_score(
                run_output
            ), run_output.intermediate_outputs
        else:
            return self.build_g_eval_score(run_output), run_output.intermediate_outputs

    def build_llm_as_judge_score(self, run_output: RunOutput) -> EvalScores:
        """
        Build the LLM as Judge score for the given run and run output.
        """
        # Convert the output format we asked for (discreet values) to our float scores
        scores: EvalScores = {}
        if not isinstance(run_output.output, dict):
            raise ValueError("LLM as Judge output must be a dictionary")

        for metric, score in run_output.output.items():
            token_score = self.score_from_token_string(f"{score}")
            if token_score is None:
                raise ValueError(
                    f"No score found for metric: {metric}. The LLM failed to follow the scoring rubric/instructions/schema."
                )
            scores[metric] = token_score
        return scores

    def build_g_eval_score(self, run_output: RunOutput) -> EvalScores:
        """
        Build the G-Eval score for the given run and run output.

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
        # We use structured output
        outputs = run_output.output
        assert isinstance(outputs, dict)

        # Build raw string output from the logprobs, which is easier to work with than Dict for the next bit
        raw_output = self.raw_output_from_logprobs(run_output)

        # find the offset the start of each metric in the raw output json
        metrics: List[str] = list(outputs.keys())
        metric_offsets = self.metric_offsets(raw_output, metrics)

        final_scores: EvalScores = {}
        for metric in metrics:
            score = self.g_eval_single_metric(
                run_output, metric, metric_offsets, raw_output
            )
            if score is None:
                raise ValueError(
                    f"No score found for metric: {metric}. The LLM failed to follow the scoring rubric/instructions/schema."
                )
            final_scores[metric] = score

        return final_scores

    def g_eval_single_metric(
        self,
        run_output: RunOutput,
        metric: str,
        metric_offsets: Dict[str, int],
        raw_output: str,
    ) -> float | None:
        """
        Run the G-Eval for a single metric.

        Scan the logprobs for the metric and return the weighted score of the rating token.
        """

        start_offset, end_offset = self.token_search_range(
            raw_output, metric, metric_offsets
        )

        offset = 0

        if (
            run_output.output_logprobs is None
            or run_output.output_logprobs.content is None
        ):
            raise RuntimeError(
                "No logprobs found for output - can not calculate g-eval"
            )

        # scan the tokens in the range, looking for the rating token
        for _, chat_logprob in enumerate(run_output.output_logprobs.content):
            if offset >= end_offset:
                break
            if offset >= start_offset:
                score = self.rating_token_to_score(chat_logprob)
                if score is not None:
                    return score
            offset += len(chat_logprob.token)

        return None

    def raw_output_from_logprobs(self, run_output: RunOutput) -> str:
        """
        Build the raw output string from the logprobs. Generate from logprobs so it's guaranteed to match the logprobs offsets
        """
        if (
            run_output.output_logprobs is None
            or run_output.output_logprobs.content is None
        ):
            raise RuntimeError(
                "No logprobs found for output - can not calculate g-eval"
            )

        raw = ""
        for chat_logprob in run_output.output_logprobs.content:
            raw += chat_logprob.token
        return raw

    def token_search_range(
        self, raw_output: str, metric: str, metric_offsets: Dict[str, int]
    ) -> Tuple[int, int]:
        """
        Find the start and end offsets of the metric in the raw output.

        Start searching after the end of the target metric json entry ("overall_rating":), and before the start of the next metric ("some_other_score").
        """
        start_offset = metric_offsets[metric] + len(metric)

        # Find the lowest end offset that is greater than the start offset
        end_offset = len(raw_output)
        for v in list(metric_offsets.values()):
            if v < end_offset and v > start_offset:
                end_offset = v

        return start_offset, end_offset

    def rating_token_to_score(
        self, token_logprob: ChatCompletionTokenLogprob
    ) -> float | None:
        """
        Convert a rating token to a score using weighted average of top logprobs.

        Only includes tokens that have valid scores.

        Some cleanup for upper case, whitespace and quotes. LLMs aren't always consistent.
        """
        primary_token_score = self.score_from_token_string(token_logprob.token)
        # check this is a real rating token, it could just be the ": ", "," or whitespace
        if not primary_token_score:
            return None

        total_score = 0.0
        total_probability = 0.0
        top_logprobs_contains_primary_token = False

        # Process all valid scoring tokens from alternatives
        for top_logprob in token_logprob.top_logprobs:
            if top_logprob.token == token_logprob.token:
                top_logprobs_contains_primary_token = True
            token_score = self.score_from_token_string(top_logprob.token)
            if token_score is not None:
                # Convert logprob to probability
                probability = math.exp(top_logprob.logprob)
                total_score += token_score * probability
                total_probability += probability

        # Weird OpenAI 4o bug - sometimes the primary token is included in the top logprobs, sometimes not.
        # Add the primary token back in if excluded
        if not top_logprobs_contains_primary_token:
            if token_logprob.logprob == -9999.0:
                # Another "bug" - sometimes the logprob is -9999.0. This seems to happen when the rest of the logprobs are tiny probability.
                total_score += primary_token_score * 1.0
                total_probability += 1.0
            else:
                probability = math.exp(token_logprob.logprob)
                total_score += primary_token_score * probability
                total_probability += probability

        if total_probability <= 0.0:
            raise RuntimeError(
                f"No valid scoring tokens found for {token_logprob.token}. This should never happen as the token has a valid score (so it must be excluded from top logprobs). Please file a bug if you see this."
            )

        # Normalize by total probability of valid tokens (LLM may have wanted to generate other non-rating tokens, these shouldn't lower score of rating tokens)
        weighted_score = total_score / total_probability

        return weighted_score

    def score_from_token_string(self, token: str) -> float | None:
        if token in TOKEN_TO_SCORE_MAP:
            return TOKEN_TO_SCORE_MAP[token]

        # handle more token variations like '"1"' and '"pass"' and ' paSS' and 'PASS'
        unquoted_token = token.strip().strip('"').lower()
        if unquoted_token in TOKEN_TO_SCORE_MAP:
            return TOKEN_TO_SCORE_MAP[unquoted_token]

        # handle numeric tokens like "1.0"
        try:
            float_value = float(token)
            if float_value.is_integer():
                str_token = str(int(float_value))
                if str_token in TOKEN_TO_SCORE_MAP:
                    return TOKEN_TO_SCORE_MAP[str_token]
        except ValueError:
            pass

        return None

    def metric_offsets(self, raw_output: str, metrics: List[str]) -> Dict[str, int]:
        """
        Find the offset to the start of each metric in the raw output json

        For the example json: `{"overall_rating": 1}` == 1

        should return:
        {
            "overall_rating": 1 # it's 1 character into the json string
        }
        """
        metric_offsets: Dict[str, int] = {}
        for metric in metrics:
            # the quoted metric name is expected in the json: `{"overall_rating": 1}` == 1
            metric_name = f'"{metric}"'

            # we expect it exactly once
            count = raw_output.count(metric_name)
            if count != 1:
                raise ValueError(
                    f"Metric {metric} should appear exactly once in the output. Found {count} times"
                )

            offset = raw_output.find(metric_name)
            if offset == -1:
                raise ValueError(f"Metric {metric} not found in raw output")
            metric_offsets[metric] = offset
        return metric_offsets
