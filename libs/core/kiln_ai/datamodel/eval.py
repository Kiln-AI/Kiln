import json
from enum import Enum
from threading import Lock
from typing import TYPE_CHECKING, Annotated, Any, Dict, List, Literal, Union

from pydantic import (
    BaseModel,
    Discriminator,
    Field,
    JsonValue,
    ValidationInfo,
    model_validator,
)
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    FilenameString,
    FilenameStringShort,
    KilnParentedModel,
    KilnParentModel,
)
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.dataset_filters import DatasetFilterId, EvalInputFilterId
from kiln_ai.datamodel.json_schema import string_to_json_key
from kiln_ai.datamodel.task_run import Usage
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

if TYPE_CHECKING:
    from kiln_ai.datamodel.spec import Spec
    from kiln_ai.datamodel.task import Task
    from kiln_ai.datamodel.task_run import TaskRun

EvalScores = Dict[str, float]

# Module-level set to track evals currently being migrated (to prevent recursion)
# Protected by _migration_lock to ensure thread-safe access
_migration_lock = Lock()
_currently_migrating_eval_ids: set[ID_TYPE] = set()


class EvalTemplateId(str, Enum):
    """
    An eval template is a pre-defined eval that can be used as a starting point for a new eval.
    """

    kiln_requirements = "kiln_requirements"
    desired_behaviour = "desired_behaviour"
    issue = "kiln_issue"
    tool_call = "tool_call"
    toxicity = "toxicity"
    bias = "bias"
    maliciousness = "maliciousness"
    factual_correctness = "factual_correctness"
    jailbreak = "jailbreak"
    rag = "rag"


class EvalConfigType(str, Enum):
    """The type of eval configuration, determining how scores are generated."""

    g_eval = "g_eval"
    llm_as_judge = "llm_as_judge"
    v2 = "v2"


class V2EvalType(str, Enum):
    """V2-only eval type enum. Each value maps to a typed properties class
    and a V2 adapter."""

    llm_judge = "llm_judge"
    exact_match = "exact_match"
    pattern_match = "pattern_match"
    set_check = "set_check"
    tool_call_check = "tool_call_check"
    contains = "contains"
    step_count_check = "step_count_check"
    code_eval = "code_eval"


class LlmJudgeProperties(BaseModel):
    type: Literal[V2EvalType.llm_judge] = V2EvalType.llm_judge
    model_name: str
    model_provider: str
    system_prompt: str | None = None
    prompt_template: str
    required_var: list[str] = []
    thinking_instruction: str | None = None
    g_eval: bool = False


class ExactMatchProperties(BaseModel):
    type: Literal[V2EvalType.exact_match] = V2EvalType.exact_match
    value_expression: str | None = None
    expected_value: str | None = None
    reference_key: str | None = Field(default=None, min_length=1)
    case_sensitive: bool = True

    @model_validator(mode="after")
    def validate_value_source(self) -> Self:
        if (self.expected_value is None) == (self.reference_key is None):
            raise ValueError(
                "Exactly one of expected_value or reference_key must be set"
            )
        return self


class PatternMatchProperties(BaseModel):
    type: Literal[V2EvalType.pattern_match] = V2EvalType.pattern_match
    value_expression: str | None = None
    pattern: str
    mode: Literal["must_match", "must_not_match"] = "must_match"

    @model_validator(mode="after")
    def validate_pattern(self) -> Self:
        import re

        try:
            re.compile(self.pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{self.pattern}': {e}") from e
        return self


class ContainsProperties(BaseModel):
    type: Literal[V2EvalType.contains] = V2EvalType.contains
    value_expression: str | None = None
    substring: str | None = None
    reference_key: str | None = Field(default=None, min_length=1)
    case_sensitive: bool = True
    mode: Literal["must_contain", "must_not_contain"] = "must_contain"

    @model_validator(mode="after")
    def validate_value_source(self) -> Self:
        if (self.substring is None) == (self.reference_key is None):
            raise ValueError("Exactly one of substring or reference_key must be set")
        return self


class SetCheckProperties(BaseModel):
    type: Literal[V2EvalType.set_check] = V2EvalType.set_check
    value_expression: str | None = None
    expected_set: list[str] | None = None
    reference_key: str | None = Field(default=None, min_length=1)
    mode: Literal["subset", "superset", "equal"]

    @model_validator(mode="after")
    def validate_value_source(self) -> Self:
        if (self.expected_set is None) == (self.reference_key is None):
            raise ValueError("Exactly one of expected_set or reference_key must be set")
        return self


class ArgMatch(BaseModel):
    value: JsonValue
    match_mode: Literal["exact", "contains", "regex"] = "exact"

    @model_validator(mode="after")
    def validate_regex(self) -> Self:
        if self.match_mode == "regex":
            import re

            try:
                re.compile(str(self.value))
            except re.error as e:
                raise ValueError(f"Invalid regex value '{self.value}': {e}") from e
        return self


class ToolCallSpec(BaseModel):
    tool_name: str
    expected_args: dict[str, ArgMatch] | None = None


class ToolCallCheckProperties(BaseModel):
    type: Literal[V2EvalType.tool_call_check] = V2EvalType.tool_call_check
    expected_tools: list[ToolCallSpec] = Field(min_length=1)
    match_mode: Literal["any", "all", "ordered", "never"] = "all"
    on_unexpected_tools: Literal["ignore", "fail"] = "ignore"


class StepCountCheckProperties(BaseModel):
    type: Literal[V2EvalType.step_count_check] = V2EvalType.step_count_check
    count_type: Literal["tool_calls", "model_responses", "turns"]
    min_count: int | None = None
    max_count: int | None = None

    @model_validator(mode="after")
    def check_bounds(self) -> Self:
        if self.min_count is None and self.max_count is None:
            raise ValueError(
                "step_count_check requires at least one of min_count / max_count"
            )
        if (
            self.min_count is not None
            and self.max_count is not None
            and self.min_count > self.max_count
        ):
            raise ValueError("min_count must be <= max_count")
        return self


class CodeEvalProperties(BaseModel):
    type: Literal[V2EvalType.code_eval] = V2EvalType.code_eval
    code: str
    timeout_seconds: int = Field(default=30, ge=1, le=300)

    @model_validator(mode="after")
    def validate_code(self) -> Self:
        code_bytes = self.code.encode("utf-8")
        if len(code_bytes) > 64 * 1024:
            raise ValueError(
                f"Code is too large ({len(code_bytes)} bytes). Maximum size is 64KB."
            )

        try:
            compile(self.code, "<code_eval>", "exec")
        except SyntaxError as e:
            raise ValueError(f"Code has a syntax error: {e}") from e

        import ast

        tree = ast.parse(self.code)
        has_score_fn = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "score"
            for node in ast.iter_child_nodes(tree)
        )
        if not has_score_fn:
            raise ValueError(
                "Code must define a module-level 'score' function (def score(...))."
            )

        return self


V2EvalConfigProperties = Annotated[
    Union[
        LlmJudgeProperties,
        ExactMatchProperties,
        PatternMatchProperties,
        SetCheckProperties,
        ToolCallCheckProperties,
        ContainsProperties,
        StepCountCheckProperties,
        CodeEvalProperties,
    ],
    Discriminator("type"),
]

# Explicit tuple of V2 property types for isinstance() checks.
# Must list exactly the same types as the V2EvalConfigProperties union above.
V2_PROPERTY_TYPES: tuple[type[BaseModel], ...] = (
    LlmJudgeProperties,
    ExactMatchProperties,
    PatternMatchProperties,
    SetCheckProperties,
    ToolCallCheckProperties,
    ContainsProperties,
    StepCountCheckProperties,
    CodeEvalProperties,
)


def validate_scores_against_output_scores(
    scores: EvalScores,
    output_scores: list["EvalOutputScore"],
) -> list[str]:
    """Validate that *scores* fall within the expected range for each output score.

    Returns a list of human-readable problem strings (empty list means all OK).
    This is a pure function — it does NOT raise; callers decide how to surface errors.
    """

    def _is_numeric(v: object) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    problems: list[str] = []
    for output_score in output_scores:
        key = output_score.json_key()
        if key not in scores:
            continue
        value = scores[key]

        match output_score.type:
            case TaskOutputRatingType.five_star:
                if not _is_numeric(value) or value < 1.0 or value > 5.0:
                    problems.append(
                        f"Score {output_score.name} is a five_star rating and must be a number between 1.0 and 5.0 inclusive. Got: {value}"
                    )
            case TaskOutputRatingType.pass_fail:
                if not _is_numeric(value) or value < 0.0 or value > 1.0:
                    problems.append(
                        f"Score {output_score.name} is a pass_fail rating and must be a number between 0.0 and 1.0 inclusive. Got: {value}"
                    )
            case TaskOutputRatingType.pass_fail_critical:
                if not _is_numeric(value) or value < -1.0 or value > 1.0:
                    problems.append(
                        f"Score {output_score.name} is a pass_fail_critical rating and must be a number between -1.0 and 1.0 inclusive. Got: {value}"
                    )
            case TaskOutputRatingType.custom:
                problems.append(
                    f"Custom scores are not supported in evaluators. '{output_score.name}' was set to a custom score."
                )
            case _:
                raise_exhaustive_enum_error(output_score.type)
    return problems


class SkippedReason(str, Enum):
    """Terminal skip reasons stored as str for back/forward-compat."""

    missing_reference_key = "missing_reference_key"
    extraction_failed = "extraction_failed"
    missing_trace = "missing_trace"
    incompatible_input_shape = "incompatible_input_shape"
    code_eval_not_trusted = "code_eval_not_trusted"
    type_not_available = "type_not_available"


class V2EvalResult(BaseModel):
    """Result of a single V2 eval ``evaluate()`` call."""

    scores: EvalScores = Field(default_factory=dict)
    skipped_reason: SkippedReason | None = None
    skipped_detail: str | None = None
    intermediate_outputs: Dict[str, str] | None = None


class UserMessage(BaseModel):
    text: str


class SingleTurnEvalInputData(BaseModel):
    type: Literal["single_turn"] = "single_turn"
    user_message: UserMessage


class MultiTurnSyntheticEvalInputData(BaseModel):
    type: Literal["multi_turn_synthetic"] = "multi_turn_synthetic"
    first_message: UserMessage | None = None
    synthetic_user_info: dict[str, JsonValue] = {}


EvalInputData = Annotated[
    Union[
        SingleTurnEvalInputData,
        MultiTurnSyntheticEvalInputData,
    ],
    Discriminator("type"),
]


class EvalInput(KilnParentedModel):
    """A single evaluation input item, stored as a child of a Task.

    Each EvalInput contains the data needed to run an evaluation (e.g. a user
    message) plus optional reference data for comparison and tags for filtering.
    """

    data: EvalInputData = Field(
        description="The input data for this eval item.",
    )
    reference: dict[str, JsonValue] | None = Field(
        default=None,
        description="Optional reference data (ground truth) for this eval input, keyed by reference name.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for filtering eval inputs.",
    )


class EvalTaskInput(BaseModel):
    """The runtime data bundle passed to V2 evaluators.

    Assembled by the eval runner from an EvalInput and a task run result.
    """

    final_message: str = Field(
        description="The final model output (task output text).",
    )
    trace: list[dict[str, Any]] | None = Field(
        default=None,
        description="The full conversation trace, if available.",
    )
    reference_data: dict[str, JsonValue] | None = Field(
        default=None,
        description="Reference/ground-truth data from EvalInput.reference.",
    )
    task_input: str | None = Field(
        default=None,
        description="The original task input text.",
    )

    @classmethod
    def from_task_run(cls, task_run: "TaskRun") -> "EvalTaskInput":
        from kiln_ai.datamodel.task_run import TaskRun as _TaskRun

        if not isinstance(task_run, _TaskRun):
            raise TypeError("Expected a TaskRun instance")

        trace_data: list[dict[str, Any]] | None = None
        if task_run.trace is not None:
            trace_data = [dict(msg) for msg in task_run.trace]

        return cls(
            final_message=task_run.output.output,
            trace=trace_data,
            reference_data=None,
            task_input=task_run.input,
        )

    @classmethod
    def from_eval_input(
        cls, eval_input: "EvalInput", run_output: "TaskRun"
    ) -> "EvalTaskInput":
        from kiln_ai.datamodel.task_run import TaskRun as _TaskRun

        if not isinstance(run_output, _TaskRun):
            raise TypeError("Expected a TaskRun instance for run_output")
        if not isinstance(eval_input, EvalInput):
            raise TypeError("Expected an EvalInput instance")

        trace_data: list[dict[str, Any]] | None = None
        if run_output.trace is not None:
            trace_data = [dict(msg) for msg in run_output.trace]

        if not isinstance(eval_input.data, SingleTurnEvalInputData):
            raise ValueError("from_eval_input only supports single-turn EvalInput")

        return cls(
            final_message=run_output.output.output,
            trace=trace_data,
            reference_data=eval_input.reference,
            task_input=eval_input.data.user_message.text,
        )


class EvalOutputScore(BaseModel):
    """
    A definition of a score that an evaluator will produce.

    Very similar to TaskRequirement, but conceptually different keeping in a separate models.
    """

    name: FilenameStringShort = Field(
        description="The name of the score. Will be provided to the model so use a descriptive name. Should align to the model's TaskRequirement name if you want to use human evals to evaluate the evaluator's performance."
    )
    instruction: str | None = Field(
        default=None,
        description="A description of the score, used to help the model understand the goal of the score. Will be provided to evaluator models, so should be written for the model, not the team/user.",
    )
    type: TaskOutputRatingType = Field(
        description="The type of rating to use ('five_star', 'pass_fail', 'pass_fail_critical').",
    )

    def json_key(self) -> str:
        """
        The JSON key for the score, used when running the evaluator with a LLM and we need JSON output.

        For example, "Overall Rating" -> "overall_rating"
        """
        return string_to_json_key(self.name)

    @model_validator(mode="after")
    def validate_type(self) -> Self:
        if self.type == TaskOutputRatingType.custom:
            raise ValueError(
                f"Custom scores are not supported in evaluators. Score '{self.name}' was set to a custom score."
            )
        return self


class EvalRun(KilnParentedModel):
    """
    The results of running an eval on a single dataset item.

    This is a child of an EvalConfig, which specifies how the scores were generated.

    Eval runs can be one of 2 types:
    1) eval_config_eval=False: we were evaluating a task run (a method of running the task). We get the task input from the dataset_id.input, run the task with the task_run_config, then ran the evaluator on that output. task_run_config_id must be set. The output saved in this model is the output of the task run.
    2) eval_config_eval=True: we were evaluating an eval config (a method of evaluating the task). We used the existing dataset item input/output, and ran the evaluator on it. task_run_config_id must be None. The input/output saved in this model is the input/output of the dataset item.
    """

    dataset_id: ID_TYPE | None = Field(
        default=None,
        description="The ID of the dataset item (TaskRun) that was used for this run. Mutually exclusive with eval_input_id.",
    )
    task_run_config_id: ID_TYPE | None = Field(
        description="The ID of the TaskRunConfig that was run, if this eval run was based on a task run. Must belong to the same Task as this eval. Can be None if this eval run is based on an eval config."
    )
    eval_config_eval: bool = Field(
        description="Whether this eval run to evaluate the parent eval config (evaluating the config using an existing dataset item). If true, task_run_config_id must be None, as we're not running the task.",
        default=False,
    )
    input: str = Field(
        description="The input to the task. JSON formatted for structured input, plaintext for unstructured input."
    )
    output: str | None = Field(
        default=None,
        description="The output of the task. None for skipped-before-execution runs.",
    )
    reference_answer: str | None = Field(
        default=None,
        description="The reference answer for the input. JSON formatted for structured reference answer, plaintext for unstructured reference answer. Used for reference answer evals.",
    )
    intermediate_outputs: Dict[str, str] | None = Field(
        default=None,
        description="The intermediate outputs of the task (example, eval thinking).",
    )
    task_run_trace: str | None = Field(
        default=None,
        description="The JSON formatted trace of the task run that produced the output.",
    )
    scores: EvalScores = Field(
        default={},
        description="The output scores of the evaluator (aligning to those required by the grand-parent Eval this object is a child of).",
    )
    task_run_usage: Usage | None = Field(
        default=None,
        description="The usage of the task run that produced this eval run output (not the usage by the evaluation model).",
    )

    eval_input_id: ID_TYPE | None = Field(
        default=None,
        description="ID of the EvalInput used for this run (V2 evals). Mutually exclusive with dataset_id.",
    )
    reference_data: dict[str, JsonValue] | None = Field(
        default=None,
        description="Structured reference data from EvalInput.reference, used by V2 eval types.",
    )
    skipped_reason: str | None = Field(
        default=None,
        description="If set, this run was skipped. Stored as str for back/forward-compat; conventionally a SkippedReason value.",
    )
    skipped_detail: str | None = Field(
        default=None,
        description="Case-specific detail for skipped runs (e.g. missing key name).",
    )

    def parent_eval_config(self) -> Union["EvalConfig", None]:
        if self.parent is not None and self.parent.__class__.__name__ != "EvalConfig":
            raise ValueError("parent must be an EvalConfig")
        return self.parent  # type: ignore

    @model_validator(mode="after")
    def validate_input_source(self) -> Self:
        if (self.dataset_id is None) == (self.eval_input_id is None):
            raise ValueError(
                "Exactly one of dataset_id (V1 TaskRun source) or "
                "eval_input_id (V2 EvalInput source) must be set"
            )
        return self

    @model_validator(mode="after")
    def validate_output_fields(self) -> Self:
        parent_eval_config = self.parent_eval_config()
        if parent_eval_config and parent_eval_config.config_type == EvalConfigType.v2:
            return self
        parent_eval = parent_eval_config.parent_eval() if parent_eval_config else None
        if not parent_eval:
            return self

        if self.output is None and self.skipped_reason is None:
            raise ValueError("V1 EvalRun requires output to be set")

        evaluation_data_type = parent_eval.evaluation_data_type
        if (
            evaluation_data_type == EvalDataType.final_answer
            and self.task_run_trace is not None
        ):
            raise ValueError("final_answer runs should not set trace")
        elif (
            not self.eval_config_eval
            and evaluation_data_type == EvalDataType.full_trace
            and self.task_run_trace is None
        ):
            raise ValueError("full_trace task run eval runs should include trace")

        return self

    @model_validator(mode="after")
    def validate_eval_run_types(self) -> Self:
        if self.eval_config_eval and self.task_run_config_id is not None:
            raise ValueError(
                "task_run_config_id must be None if eval_config_eval is true"
            )
        if not self.eval_config_eval and self.task_run_config_id is None:
            raise ValueError(
                "task_run_config_id must be set if eval_config_eval is false"
            )
        return self

    @model_validator(mode="after")
    def validate_scores(self) -> Self:
        if self.skipped_reason is not None:
            return self

        if self.scores is None or len(self.scores) == 0:
            raise ValueError("scores are required, and must have at least one score.")

        parent_eval_config = self.parent_eval_config()
        eval = parent_eval_config.parent_eval() if parent_eval_config else None
        if not eval:
            return self

        output_score_keys = [score.json_key() for score in eval.output_scores]
        if set(output_score_keys) != set(self.scores.keys()):
            raise ValueError(
                f"The scores produced by the evaluator must match the scores expected by the eval. Got: [{', '.join(self.scores.keys())}] and expected: [{', '.join(output_score_keys)}]"
            )

        problems = validate_scores_against_output_scores(
            self.scores, eval.output_scores
        )
        if problems:
            raise ValueError(problems[0])
        return self

    @model_validator(mode="after")
    def validate_reference_answer(self) -> Self:
        parent_eval_config = self.parent_eval_config()
        if parent_eval_config and parent_eval_config.config_type == EvalConfigType.v2:
            return self
        parent_eval = parent_eval_config.parent_eval() if parent_eval_config else None
        if not parent_eval:
            return self

        evaluation_data_type = parent_eval.evaluation_data_type
        if (
            self.reference_answer is not None
            and evaluation_data_type is not None
            and evaluation_data_type != EvalDataType.reference_answer
        ):
            raise ValueError(
                f"reference_answer is only valid for reference answer evals. Got: {evaluation_data_type.value}"
            )
        return self


class EvalConfig(KilnParentedModel, KilnParentModel, parent_of={"runs": EvalRun}):
    """
    A configuration for running an eval. This includes anything needed to run the eval on a dataset like the prompt, model, thresholds, etc.

    A eval might have many configs, example running the same eval with 2 different models. Comparing eval results is only valid within the scope of the same config.
    """

    name: FilenameString = Field(description="The name of the eval config.")
    model_name: str | None = Field(
        default=None,
        description="The name of the model to use for this eval config. Required for legacy configs, None for V2.",
    )
    model_provider: str | None = Field(
        default=None,
        description="The provider of the model to use for this eval config. Required for legacy configs, None for V2.",
    )
    config_type: EvalConfigType = Field(
        default=EvalConfigType.g_eval,
        description="This is used to determine the type of eval to run.",
    )
    properties: V2EvalConfigProperties | dict[str, Any] | None = Field(
        default=None,
        description="Properties to be used to execute the eval config. Legacy configs use a dict; V2 configs use typed properties.",
    )

    @model_validator(mode="before")
    @classmethod
    def dispatch_properties_parsing(cls, data: Any, info: ValidationInfo) -> Any:
        # Pydantic's discriminated-union parsing would reject a plain dict for
        # `properties` because dicts don't carry a discriminator field. V1 (legacy)
        # configs store properties as an untyped dict, so we shallow-copy and
        # re-assign it here to force Pydantic to accept the dict branch of the union.
        if not isinstance(data, dict):
            return data
        config_type = data.get("config_type", "g_eval")
        if config_type != "v2":
            props = data.get("properties")
            if props is not None and isinstance(props, dict):
                data = dict(data)
                data["properties"] = props
        return data

    def parent_eval(self) -> Union["Eval", None]:
        if self.parent is not None and self.parent.__class__.__name__ != "Eval":
            raise ValueError("parent must be an Eval")
        return self.parent  # type: ignore

    def runs(self, readonly: bool = False) -> list[EvalRun]:
        return super().runs(readonly=readonly)  # type: ignore

    @model_validator(mode="after")
    def validate_properties(self) -> Self:
        if self.config_type in (EvalConfigType.g_eval, EvalConfigType.llm_as_judge):
            if not isinstance(self.properties, dict):
                raise ValueError("Legacy config properties must be a dict")
            if "eval_steps" not in self.properties or not isinstance(
                self.properties["eval_steps"], list
            ):
                raise ValueError("eval_steps is required and must be a list for g_eval")
            if "task_description" in self.properties and not isinstance(
                self.properties["task_description"], str
            ):
                raise ValueError(
                    "task_description is optional, but if provided must be a string"
                )
            if self.model_name is None or self.model_provider is None:
                raise ValueError(
                    "model_name and model_provider are required for legacy configs"
                )
            return self
        elif self.config_type == EvalConfigType.v2:
            if not isinstance(self.properties, BaseModel):
                raise ValueError("V2 config requires typed properties")
            if self.model_name is not None or self.model_provider is not None:
                raise ValueError(
                    "V2 configs must not set root-level model_name/model_provider"
                )
            return self
        else:
            raise ValueError(f"Invalid eval config type: {self.config_type}")

    @model_validator(mode="after")
    def validate_v2_templates_and_expressions(self) -> Self:
        if self.config_type != EvalConfigType.v2 or not isinstance(
            self.properties, BaseModel
        ):
            return self

        from kiln_ai.utils.jinja_engine import (
            compile_expression_or_raise,
            compile_template_or_raise,
        )

        props = self.properties
        if isinstance(props, LlmJudgeProperties):
            compile_template_or_raise(props.prompt_template)
            from jinja2 import meta

            from kiln_ai.utils.jinja_engine import _template_env

            referenced = meta.find_undeclared_variables(
                _template_env.parse(props.prompt_template)
            )
            meaningful = {"final_message", "trace", "task_input"}
            if not (referenced & meaningful):
                raise ValueError(
                    "prompt_template never references the model output. "
                    "A template that uses only reference_data (or no variables) "
                    "produces the same judge prompt for every run. "
                    "Reference the output, e.g. {{ final_message }}."
                )
            for var in props.required_var:
                compile_expression_or_raise(var)

        if isinstance(
            props,
            (
                ExactMatchProperties,
                PatternMatchProperties,
                ContainsProperties,
                SetCheckProperties,
            ),
        ):
            if props.value_expression is not None:
                compile_expression_or_raise(props.value_expression)

        return self

    @model_validator(mode="after")
    def validate_json_serializable(self) -> "EvalConfig":
        if self.config_type == EvalConfigType.v2:
            return self
        if self.properties is None:
            return self
        try:
            json.dumps(self.properties, ensure_ascii=False)
        except TypeError as e:
            raise ValueError(f"Properties must be JSON serializable: {e!s}")
        return self


class EvalDataType(str, Enum):
    """The type of task output data to evaluate."""

    final_answer = "final_answer"
    full_trace = "full_trace"
    reference_answer = "reference_answer"


class Eval(KilnParentedModel, KilnParentModel, parent_of={"configs": EvalConfig}):
    """An evaluator definition that specifies what to evaluate and how scores should be produced."""

    name: FilenameString = Field(description="The name of the eval.")
    description: str | None = Field(
        default=None, description="The description of the eval"
    )
    template: EvalTemplateId | None = Field(
        default=None,
        description="The template selected when creating this eval. Useful for suggesting eval steps and output scores.",
    )
    current_config_id: ID_TYPE = Field(
        default=None,
        description="The id of the current config to use for this eval. This can be changed over time to run the same eval with different configs.",
    )
    eval_set_filter_id: DatasetFilterId | None = Field(
        default=None,
        description="The id of the dataset filter which defines which dataset items are included when running this eval (V1 TaskRun-typed).",
    )
    eval_configs_filter_id: DatasetFilterId | None = Field(
        default=None,
        description="The id of the dataset filter which defines which dataset items are included when comparing the quality of the eval configs under this eval. Should consist of dataset items with ratings.",
    )
    train_set_filter_id: DatasetFilterId | None = Field(
        default=None,
        description="The id of the dataset filter which defines which dataset items are included in the training set for fine-tuning.",
    )
    eval_input_filter_id: EvalInputFilterId | None = Field(
        default=None,
        description="Filter ID for EvalInput-backed datasets (V2). Mutually exclusive with eval_set_filter_id.",
    )
    output_scores: List[EvalOutputScore] = Field(
        description="The scores this evaluator should produce."
    )
    favourite: bool = Field(
        default=False,
        description="Whether this eval is a favourite of the user. Rendered as a star icon in the UI.",
    )
    template_properties: dict[str, str | int | bool | float] | None = Field(
        default=None,
        description="Properties to be used to execute the eval. This is template_type specific and should serialize to a json dict.",
    )
    evaluation_data_type: EvalDataType | None = Field(
        default=EvalDataType.final_answer,
        description="The output of the task run to evaluate. Can be final answer, full trace, or None for V2 evals.",
    )

    # Workaround to return typed parent without importing Task
    def parent_task(self) -> Union["Task", None]:
        if self.parent is not None and self.parent.__class__.__name__ != "Task":
            raise ValueError("parent must be a Task")
        return self.parent  # type: ignore

    def configs(self, readonly: bool = False) -> list[EvalConfig]:
        return super().configs(readonly=readonly)  # type: ignore

    # Workaround to return typed parent without importing Spec
    def associated_spec(self, readonly: bool = False) -> Union["Spec", None]:
        """
        Get the spec associated with this eval, if any.
        Returns None for legacy evals that are not associated with a spec.
        """

        task = self.parent_task()
        if not task or not self.id:
            return None

        specs = task.specs(readonly=readonly)
        for spec in specs:
            if spec.eval_id == self.id:
                return spec
        return None

    @model_validator(mode="after")
    def upgrade_old_reference_answer_eval_config(self) -> Self:
        """
        Migration: Set the first judge config as the default for existing reference answer evals that don't have a current_config_id set.

        For reference_answer evals that don't have a current_config_id set, this migration
        will set the first config (by created_at) as the default.
        """
        if self.id is None:
            return self

        # Only run during file loading
        if not self._loaded_from_file:
            return self

        # Skip if already migrated (has a current_config_id set)
        if self.current_config_id is not None:
            return self

        # Only migrate reference_answer evals
        if self.evaluation_data_type != EvalDataType.reference_answer:
            return self

        # Prevent recursion: self.configs() loads child files, which re-loads this parent
        # (see basemodel.py where we iterate_children_paths_of_parent_path calls load_from_file)
        # This causes the validator to run again, creating an infinite loop without this guard.
        with _migration_lock:
            if self.id in _currently_migrating_eval_ids:
                return self
            _currently_migrating_eval_ids.add(self.id)

        try:
            # Get the configs - these are loaded from child files
            configs_list = self.configs(readonly=True)
            if configs_list and len(configs_list) > 0:
                # Sort by created_at to get the oldest (first created) config
                sorted_configs = sorted(configs_list, key=lambda c: c.created_at)
                self.current_config_id = sorted_configs[0].id
        finally:
            with _migration_lock:
                _currently_migrating_eval_ids.discard(self.id)

        return self

    @model_validator(mode="after")
    def migrate_train_set_filter_id(self) -> Self:
        """
        Migration: Auto-create a train_set_filter_id for legacy evals that don't have one.

        Generates a tag-based filter ID from the eval name following the convention
        used by spec-based evals (e.g., "train_{name_slug}").
        """
        if self.id is None:
            return self

        if not self._loaded_from_file:
            return self

        if self.train_set_filter_id is not None:
            return self

        tag_suffix = self.name.lower().replace(" ", "_")
        self.train_set_filter_id = f"tag::train_{tag_suffix}"
        return self

    @model_validator(mode="after")
    def validate_scores(self) -> Self:
        if self.output_scores is None or len(self.output_scores) == 0:
            raise ValueError(
                "output_scores are required, and must have at least one score."
            )

        # check for duplicate names (once transformed to JSON keys)
        output_score_keys = [score.json_key() for score in self.output_scores]
        if len(output_score_keys) != len(set(output_score_keys)):
            raise ValueError(
                f"output_scores must have unique names (once transformed to JSON keys). Got: [{', '.join(output_score_keys)}]"
            )
        return self

    @model_validator(mode="after")
    def validate_filter_fields(self) -> Self:
        has_v1 = self.eval_set_filter_id is not None
        has_v2 = self.eval_input_filter_id is not None
        if has_v1 == has_v2:
            raise ValueError(
                "Exactly one of eval_set_filter_id or eval_input_filter_id must be set"
            )
        return self

    @model_validator(mode="after")
    def validate_template_properties(self) -> Self:
        if self.template is None:
            return self

        if (
            self.template is not EvalTemplateId.rag
            and self.eval_configs_filter_id is None
        ):
            raise ValueError(
                "eval_configs_filter_id is required for all templates except 'rag'"
            )

        # For spec-based evals, template_properties will be None and validation happens in the spec
        # For legacy evals, template_properties contains the data and we validate here
        if self.template_properties is None:
            return self

        # Check for properties that are required for the issue template (legacy evals only)
        if self.template == EvalTemplateId.issue:
            if "issue_prompt" not in self.template_properties or not isinstance(
                self.template_properties["issue_prompt"], str
            ):
                raise ValueError("issue_prompt is required for issue template")
            if "failure_example" in self.template_properties and not isinstance(
                self.template_properties["failure_example"], str
            ):
                raise ValueError(
                    "failure_example is optional for issue template, but if provided must be a string"
                )
            if "pass_example" in self.template_properties and not isinstance(
                self.template_properties["pass_example"], str
            ):
                raise ValueError(
                    "pass_example is optional for issue template, but if provided must be a string"
                )

        if self.template == EvalTemplateId.tool_call:
            if self.evaluation_data_type != EvalDataType.full_trace:
                raise ValueError(
                    "tool_call template should have evaluation_data_type set to full_trace"
                )
            if (
                "tool" not in self.template_properties
                or not isinstance(self.template_properties["tool"], str)
                or not self.template_properties["tool"].strip()
            ):
                raise ValueError("tool is required for tool call template")
            if "tool_function_name" not in self.template_properties or not isinstance(
                self.template_properties["tool_function_name"], str
            ):
                raise ValueError(
                    "tool_function_name is required for tool call template"
                )
            if (
                "appropriate_tool_use_guidelines" not in self.template_properties
                or not isinstance(
                    self.template_properties["appropriate_tool_use_guidelines"], str
                )
                or not self.template_properties[
                    "appropriate_tool_use_guidelines"
                ].strip()
            ):
                raise ValueError(
                    "appropriate_tool_use_guidelines is required for tool call template"
                )
            if (
                "inappropriate_tool_use_guidelines" in self.template_properties
                and not isinstance(
                    self.template_properties["inappropriate_tool_use_guidelines"], str
                )
            ):
                raise ValueError(
                    "inappropriate_tool_use_guidelines is optional for tool call template, but if provided must be a string"
                )
        return self
