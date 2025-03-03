import json
from abc import abstractmethod
from typing import Dict

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel.eval import Eval, EvalConfig, EvalScores
from kiln_ai.datamodel.json_schema import validate_schema
from kiln_ai.datamodel.task import RunConfig, TaskOutputRatingType, TaskRun
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


class BaseEval:
    """
    Base class for all evals/evaluators.

    Should be subclassed, and the run_eval method implemented.
    """

    def __init__(self, eval_config: EvalConfig, run_config: RunConfig | None):
        self.eval_config = eval_config
        eval = eval_config.parent_eval()
        if not eval:
            raise ValueError("Eval config must have a parent eval")
        self.eval = eval
        task = self.eval.parent_task()
        if not task:
            raise ValueError("Eval must have a parent task")
        self.target_task = task
        self.score_schema = BaseEval.build_score_schema(eval, allow_float_scores=True)
        self.run_config = run_config

    def model_and_provider(self) -> tuple[str, ModelProviderName]:
        model_name = self.eval_config.model_name
        provider = self.eval_config.model_provider
        if (
            not model_name
            or not provider
            or not isinstance(model_name, str)
            or not isinstance(provider, str)
            or provider not in ModelProviderName.__members__
        ):
            raise ValueError(
                "Model name and provider must be set in the eval config model properties"
            )

        return model_name, ModelProviderName(provider)

    async def run_task_and_eval(
        self, input: str
    ) -> tuple[TaskRun, EvalScores, Dict[str, str] | None]:
        """
        Runs the task on the provided run_config to generate fresh output, then runs the eval on that output.
        """
        if self.run_config is None:
            raise ValueError("Run config is required for run_task_and_eval")

        run_adapter = adapter_for_task(
            self.target_task,
            self.run_config.model_name,
            ModelProviderName(self.run_config.model_provider_name),
            base_adapter_config=AdapterConfig(allow_saving=False),
        )

        # Parse structured input if needed
        parsed_input = input
        if self.target_task.output_json_schema is not None:
            parsed_input = json.loads(input)

        # we don't save by default here. We'll save manually after validating the output
        run_output = await run_adapter.invoke(parsed_input)

        eval_output, intermediate_outputs = await self.run_eval(run_output)
        validate_schema(eval_output, self.score_schema)

        return run_output, eval_output, intermediate_outputs

    @abstractmethod
    async def run_eval(
        self, task_run: TaskRun
    ) -> tuple[EvalScores, Dict[str, str] | None]:
        """
        Runs the eval on the given task run.

        Returns a dictionary of scores which should conform to the score schema, and a dictionary of intermediate outputs (eval thinking).
        """
        pass

    @classmethod
    def build_score_schema(cls, eval: Eval, allow_float_scores: bool = False) -> str:
        """
        Build a JSON schema for the scoring output of the task requirements

        We allow 2 modes: allow_float_scores=True and allow_float_scores=False.

        allow_float_scores=False is used for the call to the model, and forces the model into selecting into discrete rating options (int 1-5, pass-fail, etc).
        allow_float_scores=True is used for final score output (for example, after we take a g-eval weighting of the model's logprobs). A pass/fail rating might return 0.75 for likely pass (as opposed to 0.99 for near certain pass), or a 1-5 score might return 3.75.
        """

        # Note: python maintains order, which is good as we want the user defined order, and overall last
        properties = {}
        for output_score in eval.output_scores:
            output_score_json_key = output_score.json_key()

            if len(output_score_json_key) == 0:
                raise ValueError(
                    f"Invalid output score name: {output_score.name}. Can not be used as JSON schema key."
                )
            property: dict[str, str | int | float | list[str] | list[int]] = {
                "title": output_score.name,
            }
            match output_score.type:
                case TaskOutputRatingType.five_star:
                    if allow_float_scores:
                        property["type"] = "number"
                        property["minimum"] = 1
                        property["maximum"] = 5
                    else:
                        property["enum"] = [1, 2, 3, 4, 5]

                    property["description"] = (
                        f"{output_score.instruction}\n\nThe rating should be between 1 and 5, with 1 being the worst and 5 being the best."
                    )
                case TaskOutputRatingType.pass_fail:
                    if allow_float_scores:
                        property["type"] = "number"
                        property["minimum"] = 0
                        property["maximum"] = 1
                        property["description"] = (
                            f"{output_score.instruction}\n\nThe rating should be between 0 and 1, with 0 being a failure and 1 being a pass."
                        )
                    else:
                        property["enum"] = ["pass", "fail"]
                        property["description"] = (
                            f"{output_score.instruction}\n\nThe rating should be either 'pass' or 'fail'."
                        )
                case TaskOutputRatingType.pass_fail_critical:
                    if allow_float_scores:
                        property["type"] = "number"
                        property["minimum"] = -1
                        property["maximum"] = 1
                        property["description"] = (
                            f"{output_score.instruction}\n\nThe rating should be between -1 and 1, with 1 being a pass, 0 being a failure, and -1 being a critical failure (very severe failure)."
                        )
                    else:
                        property["enum"] = ["pass", "fail", "critical"]
                        property["description"] = (
                            f"{output_score.instruction}\n\nThe rating should be either 'pass', 'fail', or 'critical' where critical a very severe failure."
                        )
                case TaskOutputRatingType.custom:
                    # Skip custom rating types in evals
                    continue
                case _:
                    raise_exhaustive_enum_error(output_score.type)

            properties[output_score_json_key] = property

        schema = {
            "type": "object",
            "properties": properties,
            "required": list(properties.keys()),
        }
        return json.dumps(schema, ensure_ascii=False)
