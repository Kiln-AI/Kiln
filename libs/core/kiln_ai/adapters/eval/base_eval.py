import json
from abc import abstractmethod
from typing import Dict, get_args

from pydantic import BaseModel

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, SkillsDict
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalInput,
    EvalScores,
    EvalTaskInput,
    SingleTurnEvalInputData,
    SkippedReason,
    V2EvalConfigProperties,
)
from kiln_ai.datamodel.json_schema import validate_schema_with_value_error
from kiln_ai.datamodel.task import RunConfigProperties, TaskOutputRatingType, TaskRun
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

_V2_PROPERTY_TYPES: tuple[type[BaseModel], ...] = get_args(
    get_args(V2EvalConfigProperties)[0]
)


def model_and_provider_from_config(
    eval_config: EvalConfig,
) -> tuple[str, ModelProviderName]:
    """Extract and validate model name and provider from an EvalConfig.

    Standalone helper so that V2 non-LLM adapters can skip calling it.
    """
    model_name = eval_config.model_name
    provider = eval_config.model_provider
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


class BaseEval:
    """
    Base class for all evals/evaluators.

    Should be subclassed, and the run_eval method implemented.
    """

    def __init__(
        self,
        eval_config: EvalConfig,
        run_config: RunConfigProperties | None,
        skills: SkillsDict | None = None,
    ):
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
        self.skills = skills

    def model_and_provider(self) -> tuple[str, ModelProviderName]:
        return model_and_provider_from_config(self.eval_config)

    async def run_task(self, eval_job_item: TaskRun | EvalInput) -> TaskRun:
        """
        Runs the task on the provided run_config to generate fresh output.
        """
        if self.run_config is None:
            raise ValueError("Run config is required for run_task_and_eval")

        run_adapter = adapter_for_task(
            self.target_task,
            self.run_config,
            base_adapter_config=AdapterConfig(
                allow_saving=False,
                skills=self.skills,
            ),
        )

        if isinstance(eval_job_item, EvalInput):
            if not isinstance(eval_job_item.data, SingleTurnEvalInputData):
                raise ValueError("run_task only supports single-turn EvalInput")
            raw_input = eval_job_item.data.user_message.text
        else:
            raw_input = eval_job_item.input

        parsed_input: str | dict = raw_input
        if self.target_task.input_json_schema is not None:
            parsed_input = json.loads(raw_input)

        return await run_adapter.invoke(parsed_input)

    async def run_task_and_eval(
        self, eval_job_item: TaskRun
    ) -> tuple[TaskRun, EvalScores, Dict[str, str] | None]:
        """
        Runs the task on the provided run_config to generate fresh output, then runs the eval on that output.
        """
        run_output = await self.run_task(eval_job_item)

        eval_output, intermediate_outputs = await self.run_eval(
            run_output, eval_job_item
        )

        validate_schema_with_value_error(
            eval_output, self.score_schema, "Eval output does not match score schema."
        )

        return run_output, eval_output, intermediate_outputs

    @abstractmethod
    async def run_eval(
        self, task_run: TaskRun, eval_job_item: TaskRun | None = None
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
                        property["type"] = "integer"
                        property["minimum"] = 1
                        property["maximum"] = 5

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
                        property["type"] = "string"
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
                        property["type"] = "string"
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
            "additionalProperties": False,
        }
        return json.dumps(schema, ensure_ascii=False)


class BaseV2EvalBridge(BaseEval):
    """Thin BaseEval subclass for V2 eval adapters.

    V2 adapters implement ``evaluate(EvalTaskInput)`` (synchronous scoring logic).
    This bridge wires that into the shared ``run_eval`` pipeline so V2 adapters
    gain fresh-generation support via ``run_task_and_eval`` without duplicating
    infrastructure.
    """

    def __init__(
        self,
        eval_config: EvalConfig,
        run_config: RunConfigProperties | None = None,
        skills: SkillsDict | None = None,
    ) -> None:
        if eval_config.config_type != EvalConfigType.v2:
            raise ValueError("V2 eval requires a V2 config_type")
        if not isinstance(eval_config.properties, _V2_PROPERTY_TYPES):
            raise ValueError("V2 eval requires typed V2 properties")
        self.properties = eval_config.properties
        super().__init__(eval_config, run_config, skills)

    @abstractmethod
    async def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]: ...

    async def run_eval(
        self, task_run: TaskRun, eval_job_item: TaskRun | None = None
    ) -> tuple[EvalScores, Dict[str, str] | None]:
        eval_task_input = EvalTaskInput.from_task_run(task_run)
        scores, skipped_reason, skipped_detail = await self.evaluate(eval_task_input)
        if skipped_reason is not None:
            raise ValueError(
                f"V2 eval was skipped ({skipped_reason}): {skipped_detail}"
            )
        return scores, None
