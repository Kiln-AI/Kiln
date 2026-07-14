import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.basemodel import KilnParentModel
from kiln_ai.datamodel.eval import (
    ArgMatch,
    CodeEvalProperties,
    ContainsProperties,
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalInput,
    EvalOutputScore,
    EvalRun,
    EvalTaskInput,
    EvalTemplateId,
    ExactMatchProperties,
    LlmJudgeProperties,
    MultiTurnSyntheticEvalInputData,
    PatternMatchProperties,
    SetCheckProperties,
    SingleTurnEvalInputData,
    SkippedReason,
    StepCountCheckProperties,
    ToolCallCheckProperties,
    ToolCallSpec,
    UserMessage,
    V2EvalResult,
    reference_data_keys,
    validate_scores_against_output_scores,
)
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_output import TaskOutputRatingType


@pytest.fixture
def mock_task():
    return Task(name="Test Task", instruction="Test instruction")


@pytest.fixture
def valid_eval_config_data():
    return {
        "name": "Test Eval Config",
        "config_type": EvalConfigType.g_eval,
        "properties": {"eval_steps": ["step1", "step2"]},
        "model_name": "gpt-4",
        "model_provider": "openai",
    }


@pytest.fixture
def valid_eval_config(valid_eval_config_data):
    return EvalConfig(**valid_eval_config_data)


def test_eval_config_valid(valid_eval_config):
    assert valid_eval_config.name == "Test Eval Config"
    assert valid_eval_config.config_type == EvalConfigType.g_eval
    assert valid_eval_config.properties["eval_steps"] == ["step1", "step2"]
    assert valid_eval_config.model_name == "gpt-4"
    assert valid_eval_config.model_provider == "openai"


def test_eval_config_missing_eval_steps(valid_eval_config):
    with pytest.raises(
        ValueError, match="eval_steps is required and must be a list for g_eval"
    ):
        valid_eval_config.properties = {}


def test_eval_config_missing_task_description(valid_eval_config):
    with pytest.raises(
        ValueError,
        match="task_description is optional, but if provided must be a string",
    ):
        valid_eval_config.properties = {"task_description": 123, "eval_steps": []}


def test_eval_config_invalid_json(valid_eval_config):
    class InvalidClass:
        pass

    with pytest.raises(ValueError, match="Properties must be JSON serializable"):
        valid_eval_config.properties = {
            "eval_steps": [],
            "invalid_key": InvalidClass(),
        }


def test_eval_config_invalid_eval_steps_type(valid_eval_config):
    with pytest.raises(
        ValueError, match="eval_steps is required and must be a list for g_eval"
    ):
        valid_eval_config.properties = {"eval_steps": "not a list"}


def test_eval_config_invalid_config_type(valid_eval_config):
    # Create an invalid config type using string
    with pytest.raises(ValueError):
        valid_eval_config.config_type = "invalid_type"


def test_eval_basic_properties():
    eval = Eval(
        name="Test Eval",
        description="Test Description",
        current_config_id="config123",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.five_star,
            )
        ],
    )

    assert eval.name == "Test Eval"
    assert eval.description == "Test Description"
    assert eval.current_config_id == "config123"
    assert eval.output_scores[0].name == "accuracy"
    assert eval.output_scores[0].type == TaskOutputRatingType.five_star


def test_eval_with_train_set_filter_id():
    """Test that Eval correctly stores train_set_filter_id."""
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::eval_test",
        train_set_filter_id="tag::eval_train_test",
        eval_configs_filter_id="tag::eval_golden_test",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )

    assert eval.eval_set_filter_id == "tag::eval_test"
    assert eval.train_set_filter_id == "tag::eval_train_test"
    assert eval.eval_configs_filter_id == "tag::eval_golden_test"


def test_eval_train_set_filter_id_defaults_to_none():
    """Test that train_set_filter_id defaults to None when not provided."""
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )

    assert eval.train_set_filter_id is None


def test_migrate_train_set_filter_id_on_load(mock_task, tmp_path):
    """Test that loading an eval from file auto-creates train_set_filter_id when missing."""
    task_path = tmp_path / "task.kiln"
    mock_task.path = task_path
    mock_task.save_to_file()

    eval = Eval(
        name="My Eval Name",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        train_set_filter_id=None,
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    eval.save_to_file()

    loaded_eval = Eval.load_from_file(str(eval.path))
    assert loaded_eval.train_set_filter_id == "tag::train_my_eval_name"


def test_migrate_train_set_filter_id_preserves_existing(mock_task, tmp_path):
    """Test that migration does not overwrite an existing train_set_filter_id."""
    task_path = tmp_path / "task.kiln"
    mock_task.path = task_path
    mock_task.save_to_file()

    eval = Eval(
        name="My Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        train_set_filter_id="tag::custom_train_tag",
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    eval.save_to_file()

    loaded_eval = Eval.load_from_file(str(eval.path))
    assert loaded_eval.train_set_filter_id == "tag::custom_train_tag"


def test_migrate_train_set_filter_id_not_on_new_eval():
    """Test that migration does not trigger on newly created evals (not loaded from file)."""
    eval = Eval(
        name="New Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        train_set_filter_id=None,
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    assert eval.train_set_filter_id is None


@pytest.mark.parametrize(
    "eval_name,expected_tag",
    [
        ("Simple", "tag::train_simple"),
        ("Two Words", "tag::train_two_words"),
        ("UPPER CASE", "tag::train_upper_case"),
        ("mixed Case Name", "tag::train_mixed_case_name"),
        ("already_underscored", "tag::train_already_underscored"),
    ],
)
def test_migrate_train_set_filter_id_slugification(
    mock_task, tmp_path, eval_name, expected_tag
):
    """Test that various eval names are correctly slugified into train_set_filter_id."""
    task_path = tmp_path / "task.kiln"
    mock_task.path = task_path
    mock_task.save_to_file()

    eval = Eval(
        name=eval_name,
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    eval.save_to_file()

    loaded_eval = Eval.load_from_file(str(eval.path))
    assert loaded_eval.train_set_filter_id == expected_tag


def test_eval_default_values():
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="quality",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )

    assert eval.description is None
    assert eval.current_config_id is None


def test_eval_parent_task_relationship(mock_task, valid_eval_config_data):
    eval = Eval(
        name="Test Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    config = EvalConfig(parent=eval, **valid_eval_config_data)

    assert eval.parent_task() == mock_task
    assert eval.parent == mock_task
    assert config.parent == eval
    assert config.parent_eval() == eval


def test_eval_parent_task_none():
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    assert eval.parent_task() is None


def test_eval_parent_task_wrong_type():
    # Create a non-Task parent
    class DummyParent(KilnParentModel, parent_of={}):
        pass

    with pytest.raises(ValueError):
        Eval(name="Test Eval", parent=DummyParent())


def test_eval_with_persisted_children(mock_task, valid_eval_config_data, tmp_path):
    task_path = tmp_path / "task.kiln"
    mock_task.path = task_path
    mock_task.save_to_file()

    eval = Eval(
        name="Test Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    eval.save_to_file()

    # Add config using the parent relationship
    config = EvalConfig(parent=eval, **valid_eval_config_data)
    config.save_to_file()

    run = EvalRun(
        parent=config,
        dataset_id="dataset123",
        task_run_config_id="config456",
        input='{"key": "value"}',
        output='{"result": "success"}',
        scores={"accuracy": 0.95},
    )
    run.save_to_file()

    # Test configs can be retrieved from disk
    evals = mock_task.evals()
    assert len(evals) == 1
    assert evals[0].name == "Test Eval"
    configs = evals[0].configs()
    assert len(configs) == 1
    assert configs[0].model_provider == "openai"
    assert configs[0].model_name == "gpt-4"

    # and back up
    assert configs[0].parent_eval().parent_task().path == task_path

    # Test runs can be retrieved from disk
    runs = configs[0].runs()
    assert len(runs) == 1
    assert runs[0].dataset_id == "dataset123"
    assert runs[0].task_run_config_id == "config456"
    assert runs[0].input == '{"key": "value"}'
    assert runs[0].output == '{"result": "success"}'
    assert runs[0].scores == {"accuracy": 0.95}

    # and back up
    assert runs[0].parent_eval_config().parent_eval().parent_task().path == task_path


def test_eval_run_valid_creation():
    """Test creating an EvalRun with valid data"""
    eval_run = EvalRun(
        dataset_id="dataset123",
        task_run_config_id="config456",
        input='{"key": "value"}',  # JSON formatted input
        output='{"result": "success"}',  # JSON formatted output
        scores={"accuracy": 0.95},
    )

    assert eval_run.dataset_id == "dataset123"
    assert eval_run.task_run_config_id == "config456"
    assert eval_run.input == '{"key": "value"}'
    assert eval_run.output == '{"result": "success"}'
    assert eval_run.scores == {"accuracy": 0.95}


def test_eval_run_plaintext():
    """Test creating an EvalRun with plaintext input/output"""
    eval_run = EvalRun(
        dataset_id="dataset123",
        task_run_config_id="config456",
        input="What is the capital of France?",
        output="The capital of France is Paris.",
        scores={"accuracy": 1.0},
    )

    assert eval_run.input == "What is the capital of France?"
    assert eval_run.output == "The capital of France is Paris."


def test_eval_run_missing_required_fields():
    """Test that omitting required fields raises ValidationError"""
    with pytest.raises(ValidationError) as exc_info:
        EvalRun(
            dataset_id="dataset123",
            # missing task_run_config_id
            input="test",
            output="test",
            scores={"score": 1.0},
        )

    assert "task_run_config_id" in str(exc_info.value)


def test_eval_run_invalid_scores():
    """Test that scores must be a dict of floats"""
    with pytest.raises(ValidationError):
        EvalRun(
            dataset_id="dataset123",
            task_run_config_id="config456",
            input="test",
            output="test",
            scores={"score": "not a float"},  # invalid score type
        )


def test_eval_missing_output_scores():
    """Test that eval creation fails when output_scores is missing"""
    with pytest.raises(ValidationError) as exc_info:
        Eval(
            name="Test Eval",
            eval_set_filter_id="tag::tag1",
            eval_configs_filter_id="tag::tag2",
        )
    assert "output_scores" in str(exc_info.value)


def test_eval_empty_output_scores():
    """Test that eval creation fails when output_scores is empty"""
    with pytest.raises(
        ValueError, match="output_scores are required, and must have at least one score"
    ):
        Eval(
            name="Test Eval",
            eval_set_filter_id="tag::tag1",
            eval_configs_filter_id="tag::tag2",
            output_scores=[],
        )


def test_eval_duplicate_output_scores():
    """Test that eval creation fails when output_scores has duplicate names"""
    with pytest.raises(
        ValueError,
        match="must have unique names",
    ):
        Eval(
            name="Test Eval",
            eval_set_filter_id="tag::tag1",
            eval_configs_filter_id="tag::tag2",
            output_scores=[
                EvalOutputScore(
                    name="score",
                    type=TaskOutputRatingType.five_star,
                ),
                EvalOutputScore(name="SCORE", type=TaskOutputRatingType.pass_fail),
            ],
        )


def test_eval_invalid_score_type():
    """Test that eval creation fails with invalid rating type in output_scores"""
    with pytest.raises(
        ValueError,
        match="Input should be 'five_star', 'pass_fail', 'pass_fail_critical'",
    ):
        Eval(
            name="Test Eval",
            eval_set_filter_id="tag::tag1",
            eval_configs_filter_id="tag::tag2",
            output_scores=[
                EvalOutputScore(
                    name="score",
                    type="invalid_type",
                )
            ],
        )


def test_eval_valid_output_scores():
    """Test that eval creation succeeds with valid output_scores"""
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.five_star,
            ),
            EvalOutputScore(
                name="critical_check",
                type=TaskOutputRatingType.pass_fail_critical,
            ),
            EvalOutputScore(name="basic_check", type=TaskOutputRatingType.pass_fail),
        ],
    )
    assert len(eval.output_scores) == 3
    assert eval.output_scores[0].type == TaskOutputRatingType.five_star
    assert eval.output_scores[0].name == "accuracy"
    assert eval.output_scores[1].type == TaskOutputRatingType.pass_fail_critical
    assert eval.output_scores[1].name == "critical_check"
    assert eval.output_scores[2].type == TaskOutputRatingType.pass_fail
    assert eval.output_scores[2].name == "basic_check"


def test_eval_output_score_name_validation():
    """Test that EvalOutputScore validates score names properly"""

    with pytest.raises(
        ValueError,
        match="cannot contain any of the following characters",
    ):
        EvalOutputScore(
            name="Correctness ",
            type=TaskOutputRatingType.five_star,
        )

    with pytest.raises(
        ValueError,
        match="cannot contain any of the following characters",
    ):
        EvalOutputScore(
            name=" Leading Space",
            type=TaskOutputRatingType.five_star,
        )

    with pytest.raises(
        ValueError,
        match="cannot contain any of the following characters",
    ):
        EvalOutputScore(
            name="consecutive__underscores",
            type=TaskOutputRatingType.five_star,
        )

    with pytest.raises(
        ValueError,
        match="cannot contain any of the following characters",
    ):
        EvalOutputScore(
            name="invalid/slash",
            type=TaskOutputRatingType.five_star,
        )

    with pytest.raises(
        ValueError,
        match="cannot contain any of the following characters",
    ):
        EvalOutputScore(
            name="invalid.period",
            type=TaskOutputRatingType.five_star,
        )

    with pytest.raises(ValueError, match="too long"):
        EvalOutputScore(
            name="a" * 33,
            type=TaskOutputRatingType.five_star,
        )

    valid_score = EvalOutputScore(
        name="Valid Name With Spaces",
        type=TaskOutputRatingType.five_star,
    )
    assert valid_score.name == "Valid Name With Spaces"

    max_length_score = EvalOutputScore(
        name="a" * 32,
        type=TaskOutputRatingType.five_star,
    )
    assert max_length_score.name == "a" * 32


@pytest.fixture
def valid_eval_run_data():
    return {
        "dataset_id": "dataset123",
        "task_run_config_id": "config456",
        "input": "test input",
        "output": "test output",
        "scores": {"accuracy": 4.5},
    }


def test_eval_run_five_star_score_validation(valid_eval_config, valid_eval_run_data):
    # Setup eval with five_star rating
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.five_star,
            )
        ],
    )
    valid_eval_config.parent = eval

    # Valid score
    run = EvalRun(parent=valid_eval_config, **valid_eval_run_data)
    assert run.scores["accuracy"] == 4.5

    # Invalid scores
    with pytest.raises(ValueError, match=r"must be a number between 1.0 and 5.0"):
        run = EvalRun(
            parent=valid_eval_config,
            **{**valid_eval_run_data, "scores": {"accuracy": 0.5}},
        )

    with pytest.raises(ValueError, match=r"must be a number between 1.0 and 5.0"):
        run = EvalRun(
            parent=valid_eval_config,
            **{**valid_eval_run_data, "scores": {"accuracy": 5.5}},
        )


def test_eval_run_pass_fail_score_validation(valid_eval_config, valid_eval_run_data):
    # Setup eval with pass_fail rating
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="check",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    valid_eval_config.parent = eval

    # Valid scores
    run = EvalRun(
        parent=valid_eval_config, **{**valid_eval_run_data, "scores": {"check": 1.0}}
    )
    assert run.scores["check"] == 1.0

    run = EvalRun(
        parent=valid_eval_config, **{**valid_eval_run_data, "scores": {"check": 0.0}}
    )
    assert run.scores["check"] == 0.0

    # Invalid scores
    with pytest.raises(ValueError, match=r"must be a number between 0.0 and 1.0"):
        run = EvalRun(
            parent=valid_eval_config,
            **{**valid_eval_run_data, "scores": {"check": -0.1}},
        )

    with pytest.raises(ValueError, match=r"must be a number between 0.0 and 1.0"):
        run = EvalRun(
            parent=valid_eval_config,
            **{**valid_eval_run_data, "scores": {"check": 1.1}},
        )


def test_eval_run_pass_fail_critical_score_validation(
    valid_eval_config, valid_eval_run_data
):
    # Setup eval with pass_fail_critical rating
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="critical",
                type=TaskOutputRatingType.pass_fail_critical,
            )
        ],
    )
    valid_eval_config.parent = eval

    # Valid scores
    run = EvalRun(
        parent=valid_eval_config, **{**valid_eval_run_data, "scores": {"critical": 1.0}}
    )
    assert run.scores["critical"] == 1.0

    run = EvalRun(
        parent=valid_eval_config,
        **{**valid_eval_run_data, "scores": {"critical": -1.0}},
    )
    assert run.scores["critical"] == -1.0

    # Invalid scores
    with pytest.raises(ValueError, match=r"must be a number between -1.0 and 1.0"):
        run = EvalRun(
            parent=valid_eval_config,
            **{**valid_eval_run_data, "scores": {"critical": -1.1}},
        )

    with pytest.raises(ValueError, match=r"must be a number between -1.0 and 1.0"):
        run = EvalRun(
            parent=valid_eval_config,
            **{**valid_eval_run_data, "scores": {"critical": 1.1}},
        )


def test_eval_run_score_keys_must_match(valid_eval_config, valid_eval_run_data):
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.five_star,
            ),
            EvalOutputScore(
                name="critical",
                type=TaskOutputRatingType.pass_fail_critical,
            ),
        ],
    )
    valid_eval_config.parent = eval

    # Correct
    EvalRun(
        parent=valid_eval_config,
        **{**valid_eval_run_data, "scores": {"accuracy": 4.5, "critical": 1.0}},
    )

    # Correct but wrong order still okay
    EvalRun(
        parent=valid_eval_config,
        **{**valid_eval_run_data, "scores": {"critical": 1.0, "accuracy": 4.5}},
    )

    # Missing score
    with pytest.raises(
        ValueError,
        match="The scores produced by the evaluator must match the scores expected by the eval",
    ):
        EvalRun(
            parent=valid_eval_config,
            **{**valid_eval_run_data, "scores": {"accuracy": 4.5}},
        )

    # Extra score
    with pytest.raises(
        ValueError,
        match="The scores produced by the evaluator must match the scores expected by the eval",
    ):
        EvalRun(
            parent=valid_eval_config,
            **{
                **valid_eval_run_data,
                "scores": {"accuracy": 4.5, "critical": 1.0, "extra": 1.0},
            },
        )

    # Missing score w matching count
    with pytest.raises(
        ValueError,
        match="The scores produced by the evaluator must match the scores expected by the eval",
    ):
        EvalRun(
            parent=valid_eval_config,
            **{**valid_eval_run_data, "scores": {"accuracy": 4.5, "wrong": 1.0}},
        )


def test_eval_custom_scores_allowed():
    """Custom-typed output scores are unbounded numeric metrics (tokens, cost,
    latency, counts) — valid on evals, code-eval only at scoring time."""
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="total cost usd",
                type=TaskOutputRatingType.custom,
            )
        ],
    )
    assert eval.output_scores[0].json_key() == "total_cost_usd"


@pytest.mark.parametrize(
    "config_type,properties",
    [
        (EvalConfigType.g_eval, {"eval_steps": ["step"]}),
        (EvalConfigType.llm_as_judge, {"eval_steps": ["step"]}),
    ],
    ids=["g_eval", "llm_as_judge"],
)
def test_judge_config_rejected_on_custom_score_eval(config_type, properties):
    """Judges structurally can't emit custom-typed keys — the config is
    rejected up front instead of failing every EvalRun save."""
    eval = Eval(
        name="Custom Metric Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(name="latency seconds", type=TaskOutputRatingType.custom)
        ],
    )
    with pytest.raises(ValueError, match="custom-typed"):
        EvalConfig(
            name="judge",
            config_type=config_type,
            properties=properties,
            model_name="gpt-4",
            model_provider="openai",
            parent=eval,
        )


def test_v2_llm_judge_config_rejected_on_custom_score_eval():
    eval = Eval(
        name="Custom Metric Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(name="latency seconds", type=TaskOutputRatingType.custom)
        ],
    )
    with pytest.raises(ValueError, match="custom-typed"):
        EvalConfig(
            name="judge",
            config_type=EvalConfigType.v2,
            properties=LlmJudgeProperties(
                model_name="gpt-4",
                model_provider="openai",
                prompt_template="Judge this: {{ output }}",
            ),
            parent=eval,
        )


def test_non_judge_config_allowed_on_custom_score_eval():
    eval = Eval(
        name="Custom Metric Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(name="latency seconds", type=TaskOutputRatingType.custom)
        ],
    )
    config = EvalConfig(
        name="code",
        config_type=EvalConfigType.v2,
        properties=CodeEvalProperties(code="def score(output):\n    return {}\n"),
        parent=eval,
    )
    assert config.is_llm_judge() is False


def test_eval_run_eval_config_eval_validation():
    """Test that eval_config_eval and task_run_config_id validation works correctly"""

    # Case 1: Valid configuration - eval_config_eval=True and task_run_config_id=None
    valid_run1 = EvalRun(
        dataset_id="dataset123",
        eval_config_eval=True,
        task_run_config_id=None,
        input="test input",
        output="test output",
        scores={"score": 1.0},
    )
    assert valid_run1.eval_config_eval is True
    assert valid_run1.task_run_config_id is None

    # Case 2: Valid configuration - eval_config_eval=False and task_run_config_id is set
    valid_run2 = EvalRun(
        dataset_id="dataset123",
        eval_config_eval=False,
        task_run_config_id="config456",
        input="test input",
        output="test output",
        scores={"score": 1.0},
    )
    assert valid_run2.eval_config_eval is False
    assert valid_run2.task_run_config_id == "config456"

    # Case 3: Invalid configuration - eval_config_eval=True but task_run_config_id is set
    with pytest.raises(
        ValueError, match="task_run_config_id must be None if eval_config_eval is true"
    ):
        EvalRun(
            dataset_id="dataset123",
            eval_config_eval=True,
            task_run_config_id="config456",
            input="test input",
            output="test output",
            scores={"score": 1.0},
        )

    # Case 4: Invalid configuration - eval_config_eval=False but task_run_config_id is None
    with pytest.raises(
        ValueError, match="task_run_config_id must be set if eval_config_eval is false"
    ):
        EvalRun(
            dataset_id="dataset123",
            eval_config_eval=False,
            task_run_config_id=None,
            input="test input",
            output="test output",
            scores={"score": 1.0},
        )


@pytest.mark.parametrize(
    "template_properties,should_raise,expected_error",
    [
        # Valid cases
        (
            {"issue_prompt": "Test issue prompt"},
            False,
            None,
        ),
        (
            {
                "issue_prompt": "Test issue prompt",
                "failure_example": "Test failure example",
            },
            False,
            None,
        ),
        (
            {
                "issue_prompt": "Test issue prompt",
                "failure_example": "Test failure example",
                "pass_example": "Test pass example",
            },
            False,
            None,
        ),
        (
            {
                "issue_prompt": "",
                "failure_example": "",
                "pass_example": "",
            },
            False,
            None,
        ),
        # Invalid cases
        (
            {},
            True,
            "issue_prompt is required for issue template",
        ),
        (
            {"failure_example": "Test failure example"},
            True,
            "issue_prompt is required for issue template",
        ),
        (
            {"issue_prompt": 123},
            True,
            "issue_prompt is required for issue template",
        ),
        (
            {
                "issue_prompt": "Test issue prompt",
                "failure_example": 456,
            },
            True,
            "failure_example is optional for issue template, but if provided must be a string",
        ),
        (
            {
                "issue_prompt": "Test issue prompt",
                "failure_example": "Test failure example",
                "pass_example": 789,
            },
            True,
            "pass_example is optional for issue template, but if provided must be a string",
        ),
    ],
)
def test_eval_template_properties_issue_template_validation(
    template_properties, should_raise, expected_error
):
    """Test issue template validation with various property combinations"""
    if should_raise:
        with pytest.raises(ValueError, match=expected_error):
            Eval(
                name="Test Eval",
                template=EvalTemplateId.issue,
                eval_set_filter_id="tag::tag1",
                eval_configs_filter_id="tag::tag2",
                output_scores=[
                    EvalOutputScore(
                        name="score",
                        type=TaskOutputRatingType.pass_fail,
                    )
                ],
                template_properties=template_properties,
            )
    else:
        eval = Eval(
            name="Test Eval",
            template=EvalTemplateId.issue,
            eval_set_filter_id="tag::tag1",
            eval_configs_filter_id="tag::tag2",
            output_scores=[
                EvalOutputScore(
                    name="score",
                    type=TaskOutputRatingType.pass_fail,
                )
            ],
            template_properties=template_properties,
        )
        assert eval.template == EvalTemplateId.issue
        for key, value in template_properties.items():
            assert (
                eval.template_properties is not None
                and eval.template_properties[key] == value
            )


@pytest.mark.parametrize(
    "template,template_properties",
    [
        (EvalTemplateId.kiln_requirements, {"random_property": "random_value"}),
        (EvalTemplateId.toxicity, {}),
        (EvalTemplateId.bias, {"some_property": 123}),
        (EvalTemplateId.maliciousness, {"test": True}),
        (EvalTemplateId.factual_correctness, {"score": 4.5}),
        (EvalTemplateId.jailbreak, {"prompt": "test"}),
        (
            None,
            {"issue_prompt": "This should not be validated", "failure_example": 123},
        ),
    ],
)
def test_eval_template_properties_non_validated_templates(
    template, template_properties
):
    """Test that templates without specific validation pass regardless of template_properties"""
    eval = Eval(
        name="Test Eval",
        template=template,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        template_properties=template_properties,
    )
    assert eval.template == template
    for key, value in template_properties.items():
        assert (
            eval.template_properties is not None
            and eval.template_properties[key] == value
        )


@pytest.mark.parametrize(
    "template_properties,should_raise,expected_error",
    [
        # Valid cases
        (
            {
                "tool": "search_tool",
                "tool_function_name": "search",
                "appropriate_tool_use_guidelines": "Call the tool when user asks for search",
            },
            False,
            None,
        ),
        (
            {
                "tool": "calculator",
                "tool_function_name": "calculate",
                "appropriate_tool_use_guidelines": "Call the tool for math calculations",
                "inappropriate_tool_use_guidelines": "Don't call the tool for simple math",
            },
            False,
            None,
        ),
        (
            {
                "tool": "weather_api",
                "tool_function_name": "get_weather",
                "appropriate_tool_use_guidelines": "Call the tool when user asks about weather",
            },
            False,
            None,
        ),
        (
            {
                "tool": "database_query",
                "tool_function_name": "query_db",
                "appropriate_tool_use_guidelines": "Call for data retrieval requests",
                "inappropriate_tool_use_guidelines": "Don't call for personal questions",
            },
            False,
            None,
        ),
        (
            {
                "tool": "",
                "tool_function_name": "",
                "appropriate_tool_use_guidelines": "",
                "inappropriate_tool_use_guidelines": "",
            },
            True,
            "tool is required for tool call template",
        ),
        # Invalid cases - missing required fields
        (
            {},
            True,
            "tool is required for tool call template",
        ),
        (
            {"tool_function_name": "search"},
            True,
            "tool is required for tool call template",
        ),
        (
            {"tool": "search_tool"},
            True,
            "tool_function_name is required for tool call template",
        ),
        (
            {"tool": "search_tool", "tool_function_name": "search"},
            True,
            "appropriate_tool_use_guidelines is required for tool call template",
        ),
        # Invalid cases - wrong types
        (
            {"tool": 123, "tool_function_name": "search"},
            True,
            "tool is required for tool call template",
        ),
        (
            {"tool": "search_tool", "tool_function_name": 456},
            True,
            "tool_function_name is required for tool call template",
        ),
        (
            {
                "tool": "search_tool",
                "tool_function_name": "search",
                "appropriate_tool_use_guidelines": 123,
            },
            True,
            "appropriate_tool_use_guidelines is required for tool call template",
        ),
        (
            {
                "tool": "search_tool",
                "tool_function_name": "search",
                "appropriate_tool_use_guidelines": "Call for data retrieval requests",
                "inappropriate_tool_use_guidelines": 789,
            },
            True,
            "inappropriate_tool_use_guidelines is optional for tool call template, but if provided must be a string",
        ),
    ],
)
def test_eval_template_properties_tool_call_template_validation(
    template_properties, should_raise, expected_error
):
    """Test tool call template validation with various property combinations"""
    if should_raise:
        with pytest.raises(ValueError, match=expected_error):
            Eval(
                name="Test Eval",
                template=EvalTemplateId.tool_call,
                evaluation_data_type=EvalDataType.full_trace,
                eval_set_filter_id="tag::tag1",
                eval_configs_filter_id="tag::tag2",
                output_scores=[
                    EvalOutputScore(
                        name="score",
                        type=TaskOutputRatingType.pass_fail,
                    )
                ],
                template_properties=template_properties,
            )
    else:
        eval = Eval(
            name="Test Eval",
            template=EvalTemplateId.tool_call,
            evaluation_data_type=EvalDataType.full_trace,
            eval_set_filter_id="tag::tag1",
            eval_configs_filter_id="tag::tag2",
            output_scores=[
                EvalOutputScore(
                    name="score",
                    type=TaskOutputRatingType.pass_fail,
                )
            ],
            template_properties=template_properties,
        )
        assert eval.template == EvalTemplateId.tool_call
        for key, value in template_properties.items():
            assert (
                eval.template_properties is not None
                and eval.template_properties[key] == value
            )


def test_eval_tool_call_template_requires_full_trace_evaluation_data_type():
    """Test that tool_call template requires evaluation_data_type to be full_trace"""
    valid_template_properties: dict[str, str | int | bool | float] = {
        "tool": "search_tool",
        "tool_function_name": "search",
        "appropriate_tool_use_guidelines": "Call the tool when user asks for search",
    }

    # Valid case: tool_call template with full_trace
    eval = Eval(
        name="Test Eval",
        template=EvalTemplateId.tool_call,
        evaluation_data_type=EvalDataType.full_trace,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        template_properties=valid_template_properties,
    )
    assert eval.template == EvalTemplateId.tool_call
    assert eval.evaluation_data_type == EvalDataType.full_trace

    # Invalid case: tool_call template with final_answer (default)
    with pytest.raises(
        ValueError,
        match="tool_call template should have evaluation_data_type set to full_trace",
    ):
        Eval(
            name="Test Eval",
            template=EvalTemplateId.tool_call,
            evaluation_data_type=EvalDataType.final_answer,
            eval_set_filter_id="tag::tag1",
            eval_configs_filter_id="tag::tag2",
            output_scores=[
                EvalOutputScore(
                    name="score",
                    type=TaskOutputRatingType.pass_fail,
                )
            ],
            template_properties=valid_template_properties,
        )

    # Invalid case: tool_call template with evaluation_data_type omitted (defaults to final_answer)
    with pytest.raises(
        ValueError,
        match="tool_call template should have evaluation_data_type set to full_trace",
    ):
        Eval(
            name="Test Eval",
            template=EvalTemplateId.tool_call,
            eval_set_filter_id="tag::tag1",
            eval_configs_filter_id="tag::tag2",
            output_scores=[
                EvalOutputScore(
                    name="score",
                    type=TaskOutputRatingType.pass_fail,
                )
            ],
            template_properties=valid_template_properties,
        )


@pytest.mark.parametrize(
    "template,eval_configs_filter_id,should_raise,expected_error",
    [
        # RAG template can have None
        (EvalTemplateId.rag, None, False, None),
        (EvalTemplateId.rag, "tag::tag2", False, None),
        # Other templates require eval_configs_filter_id
        (
            EvalTemplateId.issue,
            None,
            True,
            "eval_configs_filter_id is required for all templates except 'rag'",
        ),
        (
            EvalTemplateId.tool_call,
            None,
            True,
            "eval_configs_filter_id is required for all templates except 'rag'",
        ),
        (
            EvalTemplateId.kiln_requirements,
            None,
            True,
            "eval_configs_filter_id is required for all templates except 'rag'",
        ),
        (
            EvalTemplateId.toxicity,
            None,
            True,
            "eval_configs_filter_id is required for all templates except 'rag'",
        ),
        (
            EvalTemplateId.bias,
            None,
            True,
            "eval_configs_filter_id is required for all templates except 'rag'",
        ),
        (
            EvalTemplateId.maliciousness,
            None,
            True,
            "eval_configs_filter_id is required for all templates except 'rag'",
        ),
        (
            EvalTemplateId.factual_correctness,
            None,
            True,
            "eval_configs_filter_id is required for all templates except 'rag'",
        ),
        (
            EvalTemplateId.jailbreak,
            None,
            True,
            "eval_configs_filter_id is required for all templates except 'rag'",
        ),
        # None template skips template-specific validation
        (None, None, False, None),
        # Valid cases with eval_configs_filter_id provided
        (EvalTemplateId.issue, "tag::tag2", False, None),
        (EvalTemplateId.tool_call, "tag::tag2", False, None),
        (None, "tag::tag2", False, None),
    ],
)
def test_eval_configs_filter_id_validation(
    template, eval_configs_filter_id, should_raise, expected_error
):
    """Test that eval_configs_filter_id is required for all templates except 'rag'"""
    template_properties = {}
    if template == EvalTemplateId.issue:
        template_properties = {"issue_prompt": "Test issue prompt"}
    elif template == EvalTemplateId.tool_call:
        template_properties = {
            "tool": "search_tool",
            "tool_function_name": "search",
            "appropriate_tool_use_guidelines": "Call the tool when user asks for search",
        }

    eval_kwargs = {
        "name": "Test Eval",
        "template": template,
        "eval_set_filter_id": "tag::tag1",
        "eval_configs_filter_id": eval_configs_filter_id,
        "output_scores": [
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        "template_properties": template_properties,
    }

    if template == EvalTemplateId.tool_call:
        eval_kwargs["evaluation_data_type"] = EvalDataType.full_trace

    if should_raise:
        with pytest.raises(ValueError, match=expected_error):
            Eval(**eval_kwargs)
    else:
        eval = Eval(**eval_kwargs)
        assert eval.template == template
        assert eval.eval_configs_filter_id == eval_configs_filter_id


def test_eval_run_trace_property(mock_task, valid_eval_config_data, tmp_path):
    """Test EvalRun with trace property"""
    task_path = tmp_path / "task.kiln"
    mock_task.path = task_path
    mock_task.save_to_file()

    eval = Eval(
        name="Test Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        evaluation_data_type=EvalDataType.full_trace,
    )
    eval.save_to_file()

    config = EvalConfig(parent=eval, **valid_eval_config_data)
    config.save_to_file()

    trace_data = '{"messages": [{"role": "user", "content": "test"}]}'
    eval_run = EvalRun(
        parent=config,
        dataset_id="dataset123",
        task_run_config_id="config456",
        input="test input",
        output="test output",
        scores={"accuracy": 0.95},
        task_run_trace=trace_data,
    )
    eval_run.save_to_file()

    # Verify the properties are saved correctly
    assert eval_run.task_run_trace == trace_data
    assert isinstance(eval_run.task_run_trace, str)

    # Verify persistence by reloading from disk
    runs = config.runs()
    assert len(runs) == 1
    assert runs[0].task_run_trace == trace_data


def test_eval_run_new_properties_default_none(
    mock_task, valid_eval_config_data, tmp_path
):
    """Test that new properties default to None when not provided"""
    task_path = tmp_path / "task.kiln"
    mock_task.path = task_path
    mock_task.save_to_file()

    eval = Eval(
        name="Test Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    eval.save_to_file()

    config = EvalConfig(parent=eval, **valid_eval_config_data)
    config.save_to_file()

    eval_run = EvalRun(
        parent=config,
        dataset_id="dataset123",
        task_run_config_id="config456",
        input="test input",
        output="test output",
        scores={"accuracy": 0.95},
    )
    eval_run.save_to_file()

    # Verify the properties default to None
    assert eval_run.task_run_trace is None

    # Verify persistence by reloading from disk
    runs = config.runs()
    assert len(runs) == 1
    assert runs[0].task_run_trace is None


def test_eval_data_type_enum_values():
    """Test EvalDataType enum has correct values"""
    assert EvalDataType.final_answer == "final_answer"
    assert EvalDataType.full_trace == "full_trace"


def test_eval_default_evaluation_data_type():
    """Test that Eval defaults to final_answer for evaluation_data_type"""
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )

    assert eval.evaluation_data_type == EvalDataType.final_answer


def test_eval_custom_evaluation_data_type():
    """Test Eval with custom evaluation_data_type"""
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        evaluation_data_type=EvalDataType.full_trace,
    )

    assert eval.evaluation_data_type == EvalDataType.full_trace


@pytest.mark.parametrize(
    "evaluation_data_type",
    [EvalDataType.final_answer, EvalDataType.full_trace],
)
def test_eval_all_evaluation_data_types(evaluation_data_type):
    """Test Eval with all possible evaluation_data_type values"""
    eval = Eval(
        name="Test Eval",
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="score",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        evaluation_data_type=evaluation_data_type,
    )

    assert eval.evaluation_data_type == evaluation_data_type


def test_eval_run_eval_config_eval_data_type_validation(
    mock_task, valid_eval_config_data, tmp_path
):
    """Test that eval_config_eval works with all evaluation data types"""
    task_path = tmp_path / "task.kiln"
    mock_task.path = task_path
    mock_task.save_to_file()

    # Test with final_answer - should work
    eval_final_answer = Eval(
        name="Test Eval Final Answer",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        evaluation_data_type=EvalDataType.final_answer,
    )
    eval_final_answer.save_to_file()

    config_final_answer = EvalConfig(parent=eval_final_answer, **valid_eval_config_data)
    config_final_answer.save_to_file()

    # This should work - eval_config_eval with final_answer
    EvalRun(
        parent=config_final_answer,
        dataset_id="dataset123",
        eval_config_eval=True,
        task_run_config_id=None,
        input="test input",
        output="test output",
        scores={"accuracy": 0.95},
    )

    # Test with full_trace - should work
    eval_full_trace = Eval(
        name="Test Eval Full Trace",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        evaluation_data_type=EvalDataType.full_trace,
    )
    eval_full_trace.save_to_file()

    config_full_trace = EvalConfig(parent=eval_full_trace, **valid_eval_config_data)
    config_full_trace.save_to_file()

    # This should work - eval_config_eval with full_trace
    EvalRun(
        parent=config_full_trace,
        dataset_id="dataset123",
        eval_config_eval=True,
        task_run_config_id=None,
        input="test input",
        output="test output",
        scores={"accuracy": 0.95},
        task_run_trace='{"messages": [{"role": "user", "content": "test"}]}',
    )


def test_validate_output_fields_final_answer_valid_cases(
    mock_task, valid_eval_config_data
):
    """Test validate_output_fields with final_answer evaluation data type - valid cases"""
    eval = Eval(
        name="Test Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        evaluation_data_type=EvalDataType.final_answer,
    )
    config = EvalConfig(parent=eval, **valid_eval_config_data)

    # Valid case: no full_trace
    run = EvalRun(
        parent=config,
        dataset_id="dataset123",
        task_run_config_id="config456",
        input="test input",
        output="test output",
        scores={"accuracy": 0.95},
    )
    assert run.task_run_trace is None

    # Valid case: explicitly set to None
    run = EvalRun(
        parent=config,
        dataset_id="dataset123",
        task_run_config_id="config456",
        input="test input",
        output="test output",
        scores={"accuracy": 0.95},
        task_run_trace=None,
    )
    assert run.task_run_trace is None


def test_validate_output_fields_final_answer_invalid_cases(
    mock_task, valid_eval_config_data
):
    """Test validate_output_fields with final_answer evaluation data type - invalid cases"""
    eval = Eval(
        name="Test Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        evaluation_data_type=EvalDataType.final_answer,
    )
    config = EvalConfig(parent=eval, **valid_eval_config_data)

    # Invalid case: full_trace is set
    with pytest.raises(
        ValueError,
        match="final_answer runs should not set trace",
    ):
        EvalRun(
            parent=config,
            dataset_id="dataset123",
            task_run_config_id="config456",
            input="test input",
            output="test output",
            scores={"accuracy": 0.95},
            task_run_trace='{"messages": []}',
        )


def test_validate_output_fields_full_trace_valid_cases(
    mock_task, valid_eval_config_data
):
    """Test validate_output_fields with full_trace evaluation data type - valid cases"""
    eval = Eval(
        name="Test Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        evaluation_data_type=EvalDataType.full_trace,
    )
    config = EvalConfig(parent=eval, **valid_eval_config_data)

    # Valid case: full_trace is set
    run = EvalRun(
        parent=config,
        dataset_id="dataset123",
        task_run_config_id="config456",
        input="test input",
        output="test output",
        scores={"accuracy": 0.95},
        task_run_trace='{"messages": [{"role": "user", "content": "test"}]}',
    )
    assert run.task_run_trace == '{"messages": [{"role": "user", "content": "test"}]}'


def test_validate_output_fields_full_trace_invalid_cases(
    mock_task, valid_eval_config_data
):
    """Test validate_output_fields with full_trace evaluation data type - invalid cases"""
    eval = Eval(
        name="Test Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        evaluation_data_type=EvalDataType.full_trace,
    )
    config = EvalConfig(parent=eval, **valid_eval_config_data)

    # Invalid case: trace is omitted
    with pytest.raises(
        ValueError, match="full_trace task run eval runs should include trace"
    ):
        EvalRun(
            parent=config,
            dataset_id="dataset123",
            task_run_config_id="config456",
            input="test input",
            output="test output",
            scores={"accuracy": 0.95},
        )

    # Invalid case: trace is explicitly None
    with pytest.raises(
        ValueError, match="full_trace task run eval runs should include trace"
    ):
        EvalRun(
            parent=config,
            dataset_id="dataset123",
            task_run_config_id="config456",
            input="test input",
            output="test output",
            scores={"accuracy": 0.95},
            task_run_trace=None,
        )


def test_validate_output_fields_no_parent_eval(valid_eval_config_data):
    """Test validate_output_fields when there is no parent eval (should still validate mutual exclusivity)"""
    # Create a config without a parent eval
    config = EvalConfig(**valid_eval_config_data)

    # This should work - no parent eval means validation passes
    run = EvalRun(
        parent=config,
        dataset_id="dataset123",
        task_run_config_id="config456",
        input="test input",
        output="test output",
        scores={"accuracy": 0.95},
        task_run_trace='{"messages": []}',
    )
    assert run.task_run_trace == '{"messages": []}'


def test_validate_output_fields_no_parent_eval_config():
    """Test validate_output_fields when there is no parent eval config (should pass)"""
    # Create a run without a parent
    run = EvalRun(
        dataset_id="dataset123",
        task_run_config_id="config456",
        input="test input",
        output="test output",
        scores={"accuracy": 0.95},
        task_run_trace='{"messages": []}',
    )
    assert run.task_run_trace == '{"messages": []}'


@pytest.mark.parametrize(
    "evaluation_data_type,trace,should_raise,expected_error",
    [
        # final_answer cases
        (EvalDataType.final_answer, None, False, None),
        (
            EvalDataType.final_answer,
            '{"messages": []}',
            True,
            "final_answer runs should not set trace",
        ),
        # full_trace cases
        (EvalDataType.full_trace, '{"messages": []}', False, None),
        (
            EvalDataType.full_trace,
            None,
            True,
            "full_trace task run eval runs should include trace",
        ),
    ],
)
def test_validate_output_fields_parametrized(
    mock_task,
    valid_eval_config_data,
    evaluation_data_type,
    trace,
    should_raise,
    expected_error,
):
    """Test validate_output_fields with parametrized test cases"""
    eval = Eval(
        name="Test Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        evaluation_data_type=evaluation_data_type,
    )
    config = EvalConfig(parent=eval, **valid_eval_config_data)

    run_data = {
        "parent": config,
        "dataset_id": "dataset123",
        "task_run_config_id": "config456",
        "input": "test input",
        "output": "test output",
        "scores": {"accuracy": 0.95},
    }

    if trace is not None:
        run_data["task_run_trace"] = trace

    if should_raise:
        with pytest.raises(ValueError, match=expected_error):
            EvalRun(**run_data)
    else:
        run = EvalRun(**run_data)
        assert run.task_run_trace == trace


@pytest.mark.parametrize(
    "evaluation_data_type,reference_answer,should_raise,expected_error",
    [
        # reference_answer eval type - valid cases
        (EvalDataType.reference_answer, "answer text", False, None),
        (EvalDataType.reference_answer, None, False, None),
        # final_answer eval type
        (EvalDataType.final_answer, None, False, None),
        (
            EvalDataType.final_answer,
            "answer text",
            True,
            r"reference_answer is only valid for reference answer evals\. Got: final_answer",
        ),
        # full_trace eval type
        (EvalDataType.full_trace, None, False, None),
        (
            EvalDataType.full_trace,
            "answer text",
            True,
            r"reference_answer is only valid for reference answer evals\. Got: full_trace",
        ),
    ],
)
def test_validate_reference_answer_parametrized(
    mock_task,
    valid_eval_config_data,
    evaluation_data_type,
    reference_answer,
    should_raise,
    expected_error,
):
    """Test validate_reference_answer with parametrized test cases"""
    eval = Eval(
        name="Test Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        evaluation_data_type=evaluation_data_type,
    )
    config = EvalConfig(parent=eval, **valid_eval_config_data)

    run_data = {
        "parent": config,
        "dataset_id": "dataset123",
        "task_run_config_id": "config456",
        "input": "test input",
        "output": "test output",
        "scores": {"accuracy": 0.95},
    }

    if reference_answer is not None:
        run_data["reference_answer"] = reference_answer

    if evaluation_data_type == EvalDataType.full_trace:
        run_data["task_run_trace"] = (
            '{"messages": [{"role": "user", "content": "test"}]}'
        )

    if should_raise:
        with pytest.raises(ValueError, match=expected_error):
            EvalRun(**run_data)
    else:
        run = EvalRun(**run_data)
        assert run.reference_answer == reference_answer


def test_eval_upgrade_old_reference_answer_eval_config(mock_task, tmp_path):
    """Test that reference answer evals with no current_config_id get the first config set as default."""
    # Create an eval with reference_answer type and save to disk
    task = mock_task
    task.path = tmp_path / "task.kiln"
    task.save_to_file()

    eval = Eval(
        name="Test Eval",
        parent=task,
        evaluation_data_type=EvalDataType.reference_answer,
        eval_set_filter_id="all",
        eval_configs_filter_id="high_rating",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    eval.save_to_file()

    # Create two configs with different created_at times
    from datetime import datetime, timedelta

    config1 = EvalConfig(
        parent=eval,
        name="First Config",
        model_name="gpt-4",
        model_provider="openai",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1"]},
    )
    config1.created_at = datetime.now().astimezone()
    config1.save_to_file()

    config2 = EvalConfig(
        parent=eval,
        name="Second Config",
        model_name="gpt-4",
        model_provider="openai",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1"]},
    )
    config2.created_at = datetime.now().astimezone() + timedelta(seconds=1)
    config2.save_to_file()

    # Load from file - should set the first (oldest) config as default
    loaded_eval = Eval.load_from_file(str(eval.path))
    assert loaded_eval.current_config_id == config1.id  # First by created_at

    # Test with current_config_id already set - should not change it
    eval.current_config_id = config2.id
    eval.save_to_file()
    loaded_eval = Eval.load_from_file(str(eval.path))
    assert loaded_eval.current_config_id == config2.id  # Should keep existing value

    # Test with non-reference_answer type - should not set current_config_id
    eval.evaluation_data_type = EvalDataType.final_answer
    eval.current_config_id = None
    eval.save_to_file()
    loaded_eval = Eval.load_from_file(str(eval.path))
    assert (
        loaded_eval.current_config_id is None
    )  # Should not set for non-reference_answer

    # Test with no configs - should not error
    eval.evaluation_data_type = EvalDataType.reference_answer
    eval.current_config_id = None
    eval.save_to_file()
    # Delete config files
    if config1.path is not None:
        config1.path.unlink()
    if config2.path is not None:
        config2.path.unlink()
    loaded_eval = Eval.load_from_file(str(eval.path))
    assert loaded_eval.current_config_id is None  # No configs to set


# ── V1 Characterization Tests ──────────────────────────────────────────


def test_v1_eval_config_loads_from_disk(mock_task, tmp_path):
    """Characterization: V1 g_eval config round-trips through disk without corruption."""
    task_path = tmp_path / "task.kiln"
    mock_task.path = task_path
    mock_task.save_to_file()

    eval = Eval(
        name="Chartest",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(name="accuracy", type=TaskOutputRatingType.pass_fail)
        ],
    )
    eval.save_to_file()

    config = EvalConfig(
        name="GEval Config",
        parent=eval,
        config_type=EvalConfigType.g_eval,
        model_name="gpt-4",
        model_provider="openai",
        properties={"eval_steps": ["step1", "step2"], "task_description": "desc"},
    )
    config.save_to_file()

    loaded = EvalConfig.load_from_file(str(config.path))
    assert loaded.config_type == EvalConfigType.g_eval
    assert loaded.model_name == "gpt-4"
    assert loaded.model_provider == "openai"
    assert isinstance(loaded.properties, dict)
    assert loaded.properties["eval_steps"] == ["step1", "step2"]


def test_v1_eval_run_with_reference_answer(mock_task, tmp_path):
    """Characterization: V1 eval run with a reference_answer saves and loads."""
    task_path = tmp_path / "task.kiln"
    mock_task.path = task_path
    mock_task.save_to_file()

    eval = Eval(
        name="RefAnswer Eval",
        parent=mock_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        evaluation_data_type=EvalDataType.reference_answer,
        output_scores=[
            EvalOutputScore(name="score", type=TaskOutputRatingType.pass_fail)
        ],
    )
    eval.save_to_file()

    config = EvalConfig(
        name="Ref Config",
        parent=eval,
        config_type=EvalConfigType.g_eval,
        model_name="gpt-4",
        model_provider="openai",
        properties={"eval_steps": ["check ref"]},
    )
    config.save_to_file()

    run = EvalRun(
        parent=config,
        dataset_id="ds1",
        task_run_config_id="rc1",
        input="What?",
        output="Answer",
        reference_answer="Gold answer",
        scores={"score": 0.9},
    )
    run.save_to_file()

    loaded = EvalRun.load_from_file(str(run.path))
    assert loaded.reference_answer == "Gold answer"
    assert loaded.scores == {"score": 0.9}
    assert loaded.dataset_id == "ds1"


# ── V2 EvalConfig Tests ────────────────────────────────────────────────


def test_v2_eval_config_valid():
    """V2 config with typed LlmJudgeProperties is accepted."""
    config = EvalConfig(
        name="V2 Config",
        config_type=EvalConfigType.v2,
        properties=LlmJudgeProperties(
            model_name="gpt-4o",
            model_provider="openai",
            prompt_template="Evaluate: {{ final_message }}",
        ),
    )
    assert config.config_type == EvalConfigType.v2
    assert isinstance(config.properties, LlmJudgeProperties)
    assert config.model_name is None
    assert config.model_provider is None


def test_v2_eval_config_rejects_root_model_fields():
    """V2 config must NOT set root-level model_name / model_provider."""
    with pytest.raises(ValueError, match="must not set root-level model_name"):
        EvalConfig(
            name="Bad V2",
            config_type=EvalConfigType.v2,
            model_name="gpt-4o",
            model_provider="openai",
            properties=LlmJudgeProperties(
                model_name="gpt-4o",
                model_provider="openai",
                prompt_template="t",
            ),
        )


def test_v2_eval_config_requires_typed_properties():
    """V2 config rejects a raw dict for properties."""
    with pytest.raises(ValueError, match="V2 config requires typed properties"):
        EvalConfig(
            name="Bad V2",
            config_type=EvalConfigType.v2,
            properties={"eval_steps": ["step"]},
        )


def test_legacy_config_unchanged():
    """Legacy g_eval config still validates the same as before."""
    config = EvalConfig(
        name="Legacy",
        config_type=EvalConfigType.g_eval,
        model_name="gpt-4",
        model_provider="openai",
        properties={"eval_steps": ["s1"]},
    )
    assert isinstance(config.properties, dict)


def test_legacy_config_requires_model_fields():
    """Legacy config rejects missing model_name / model_provider."""
    with pytest.raises(ValueError, match="model_name and model_provider are required"):
        EvalConfig(
            name="Legacy Missing",
            config_type=EvalConfigType.g_eval,
            properties={"eval_steps": ["s1"]},
        )


def test_v2_json_serializable_bypass():
    """V2 bypass of validate_json_serializable (which would fail for typed props)."""
    config = EvalConfig(
        name="V2 Bypass",
        config_type=EvalConfigType.v2,
        properties=ExactMatchProperties(expected_value="hello"),
    )
    assert config.config_type == EvalConfigType.v2


def test_v2_eval_config_discriminated_union_dispatch():
    """V2 properties discriminated union dispatches by type field."""
    config = EvalConfig(
        name="Pattern",
        config_type=EvalConfigType.v2,
        properties=PatternMatchProperties(pattern=r"\\d+"),
    )
    assert isinstance(config.properties, PatternMatchProperties)

    config2 = EvalConfig(
        name="Contains",
        config_type=EvalConfigType.v2,
        properties=ContainsProperties(substring="hello"),
    )
    assert isinstance(config2.properties, ContainsProperties)


# ── V2 EvalConfig Properties Validators ────────────────────────────────


def test_exact_match_xor_validator():
    """ExactMatchProperties requires exactly one of expected_value/reference_key."""
    with pytest.raises(
        ValueError, match="Exactly one of expected_value or reference_key"
    ):
        ExactMatchProperties(expected_value="a", reference_key="b")
    with pytest.raises(
        ValueError, match="Exactly one of expected_value or reference_key"
    ):
        ExactMatchProperties()

    assert ExactMatchProperties(expected_value="hello").expected_value == "hello"
    assert ExactMatchProperties(reference_key="key1").reference_key == "key1"


def test_contains_xor_validator():
    """ContainsProperties requires exactly one of substring/reference_key."""
    with pytest.raises(ValueError, match="Exactly one of substring or reference_key"):
        ContainsProperties(substring="a", reference_key="b")
    with pytest.raises(ValueError, match="Exactly one of substring or reference_key"):
        ContainsProperties()


def test_set_check_xor_validator():
    """SetCheckProperties requires exactly one of expected_set/reference_key."""
    with pytest.raises(
        ValueError, match="Exactly one of expected_set or reference_key"
    ):
        SetCheckProperties(expected_set=["a"], reference_key="b", mode="equal")
    with pytest.raises(
        ValueError, match="Exactly one of expected_set or reference_key"
    ):
        SetCheckProperties(mode="subset")

    assert SetCheckProperties(expected_set=["x"], mode="equal").expected_set == ["x"]


def test_set_check_mode_required():
    """SetCheckProperties.mode is required; omitting it raises ValidationError."""
    with pytest.raises(ValidationError):
        SetCheckProperties(expected_set=["a"])


def test_set_check_mode_explicit_values():
    """Each mode value works when explicitly provided."""
    for m in ("subset", "superset", "equal"):
        props = SetCheckProperties(expected_set=["a"], mode=m)
        assert props.mode == m


def test_step_count_check_bounds():
    """StepCountCheckProperties requires at least one of min/max, min <= max."""
    with pytest.raises(ValueError, match="at least one of min_count"):
        StepCountCheckProperties(count_type="tool_calls")
    with pytest.raises(ValueError, match="min_count must be <= max_count"):
        StepCountCheckProperties(count_type="turns", min_count=5, max_count=2)

    ok = StepCountCheckProperties(count_type="model_responses", min_count=1)
    assert ok.min_count == 1
    assert ok.max_count is None


# ── V2 Eval Tests ──────────────────────────────────────────────────────


def test_eval_v2_with_eval_input_filter():
    """Eval with eval_input_filter_id (V2 path) validates correctly."""
    eval = Eval(
        name="V2 Eval",
        eval_input_filter_id="all",
        eval_configs_filter_id="tag::cfg",
        output_scores=[
            EvalOutputScore(name="score", type=TaskOutputRatingType.pass_fail)
        ],
    )
    assert eval.eval_input_filter_id == "all"
    assert eval.eval_set_filter_id is None


def test_eval_filter_mutual_exclusivity():
    """Setting both eval_set_filter_id and eval_input_filter_id raises."""
    with pytest.raises(
        ValueError, match="Exactly one of eval_set_filter_id or eval_input_filter_id"
    ):
        Eval(
            name="Both",
            eval_set_filter_id="tag::tag1",
            eval_input_filter_id="all",
            eval_configs_filter_id="tag::cfg",
            output_scores=[
                EvalOutputScore(name="s", type=TaskOutputRatingType.pass_fail)
            ],
        )

    with pytest.raises(
        ValueError, match="Exactly one of eval_set_filter_id or eval_input_filter_id"
    ):
        Eval(
            name="Neither",
            eval_configs_filter_id="tag::cfg",
            output_scores=[
                EvalOutputScore(name="s", type=TaskOutputRatingType.pass_fail)
            ],
        )


def test_eval_optional_evaluation_data_type():
    """evaluation_data_type defaults to final_answer."""
    eval = Eval(
        name="Default DT",
        eval_set_filter_id="tag::t",
        eval_configs_filter_id="tag::t2",
        output_scores=[EvalOutputScore(name="s", type=TaskOutputRatingType.pass_fail)],
    )
    assert eval.evaluation_data_type == EvalDataType.final_answer


def test_validate_template_properties_none_template():
    """When template is None, validate_template_properties returns early."""
    eval = Eval(
        name="No Template",
        eval_set_filter_id="tag::t",
        eval_configs_filter_id="tag::t2",
        template=None,
        output_scores=[EvalOutputScore(name="s", type=TaskOutputRatingType.pass_fail)],
    )
    assert eval.template is None


# ── V2 EvalRun Tests ───────────────────────────────────────────────────


def test_eval_run_v2_with_eval_input_id():
    """V2 eval run uses eval_input_id instead of dataset_id."""
    run = EvalRun(
        eval_input_id="ei_123",
        task_run_config_id="rc1",
        input="hi",
        output="hello",
        scores={"s": 1.0},
    )
    assert run.eval_input_id == "ei_123"
    assert run.dataset_id is None


def test_eval_run_input_source_xor():
    """Exactly one of dataset_id / eval_input_id must be set."""
    with pytest.raises(
        ValueError,
        match=r"Exactly one of dataset_id \(V1 TaskRun source\) or eval_input_id \(V2 EvalInput source\)",
    ):
        EvalRun(
            dataset_id="d1",
            eval_input_id="ei1",
            task_run_config_id="rc1",
            input="i",
            output="o",
            scores={"s": 1.0},
        )
    with pytest.raises(
        ValueError,
        match=r"Exactly one of dataset_id \(V1 TaskRun source\) or eval_input_id \(V2 EvalInput source\)",
    ):
        EvalRun(
            task_run_config_id="rc1",
            input="i",
            output="o",
            scores={"s": 1.0},
        )


def test_eval_run_skipped_allows_empty_scores():
    """When skipped_reason is set, empty scores are allowed."""
    run = EvalRun(
        eval_input_id="ei1",
        task_run_config_id="rc1",
        input="i",
        output="o",
        skipped_reason=SkippedReason.missing_reference_key.value,
        skipped_detail="key 'expected' not found",
        scores={},
    )
    assert run.skipped_reason == "missing_reference_key"
    assert run.scores == {}


def test_eval_run_skipped_allows_none_output():
    """Skipped runs can have None output."""
    run = EvalRun(
        eval_input_id="ei1",
        task_run_config_id="rc1",
        input="i",
        output=None,
        skipped_reason=SkippedReason.extraction_failed.value,
        scores={},
    )
    assert run.output is None


def test_eval_run_v2_bypass_output_fields():
    """V2 config_type bypasses validate_output_fields and validate_reference_answer."""
    eval = Eval(
        name="V2 Parent",
        eval_input_filter_id="all",
        eval_configs_filter_id="tag::cfg",
        evaluation_data_type=EvalDataType.final_answer,
        output_scores=[
            EvalOutputScore(name="score", type=TaskOutputRatingType.pass_fail)
        ],
    )
    config = EvalConfig(
        name="V2 Config",
        parent=eval,
        config_type=EvalConfigType.v2,
        properties=ExactMatchProperties(expected_value="hello"),
    )
    run = EvalRun(
        parent=config,
        eval_input_id="ei1",
        task_run_config_id="rc1",
        input="i",
        output="hello",
        reference_answer="should be accepted in v2",
        scores={"score": 1.0},
    )
    assert run.reference_answer == "should be accepted in v2"


def test_eval_run_not_skipped_requires_scores():
    """Non-skipped runs with empty scores raise ValueError."""
    with pytest.raises(ValueError, match="scores are required"):
        EvalRun(
            eval_input_id="ei1",
            task_run_config_id="rc1",
            input="i",
            output="o",
            scores={},
        )


# ── EvalInput Tests ────────────────────────────────────────────────────


def test_eval_input_single_turn():
    """EvalInput with single_turn data."""
    ei = EvalInput(
        data=SingleTurnEvalInputData(user_message=UserMessage(text="What is 2+2?")),
    )
    assert ei.data.type == "single_turn"
    assert ei.data.user_message.text == "What is 2+2?"


def test_eval_input_multi_turn():
    """EvalInput with multi_turn_synthetic data."""
    ei = EvalInput(
        data=MultiTurnSyntheticEvalInputData(
            first_message=UserMessage(text="Hello"),
            synthetic_user_info={"persona": "student"},
        ),
    )
    assert ei.data.type == "multi_turn_synthetic"
    assert ei.data.first_message.text == "Hello"
    assert ei.data.synthetic_user_info == {"persona": "student"}


def test_eval_input_with_reference():
    """EvalInput with reference data."""
    ei = EvalInput(
        data=SingleTurnEvalInputData(user_message=UserMessage(text="Q")),
        reference={"expected_answer": "A", "source": "textbook"},
    )
    assert ei.reference == {"expected_answer": "A", "source": "textbook"}


def test_eval_input_with_tags():
    """EvalInput with tags."""
    ei = EvalInput(
        data=SingleTurnEvalInputData(user_message=UserMessage(text="Q")),
        tags=["math", "easy"],
    )
    assert ei.tags == ["math", "easy"]


def test_eval_input_persists_under_task(mock_task, tmp_path):
    """EvalInput saves as a child of Task and loads back."""
    task_path = tmp_path / "task.kiln"
    mock_task.path = task_path
    mock_task.save_to_file()

    ei = EvalInput(
        parent=mock_task,
        data=SingleTurnEvalInputData(user_message=UserMessage(text="Persist me")),
        reference={"key": "val"},
        tags=["t1"],
    )
    ei.save_to_file()

    loaded_task = Task.load_from_file(str(task_path))
    inputs = loaded_task.eval_inputs(readonly=True)
    assert len(inputs) == 1
    assert inputs[0].data.type == "single_turn"
    assert inputs[0].data.user_message.text == "Persist me"
    assert inputs[0].reference == {"key": "val"}
    assert inputs[0].tags == ["t1"]


# ── EvalTaskInput Tests ──────────────────────────────────────────────────


class TestEvalTaskInput:
    def test_minimal(self):
        """Only final_message is required."""
        eti = EvalTaskInput(final_message="Hello world")
        assert eti.final_message == "Hello world"
        assert eti.trace is None
        assert eti.reference_data is None
        assert eti.task_input is None

    def test_all_fields(self):
        """All fields populated."""
        trace = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hey"},
        ]
        ref = {"expected": "42", "source": "textbook"}
        eti = EvalTaskInput(
            final_message="hey",
            trace=trace,
            reference_data=ref,
            task_input="hi",
        )
        assert eti.final_message == "hey"
        assert eti.trace == trace
        assert eti.reference_data == ref
        assert eti.task_input == "hi"

    def test_round_trip(self):
        """model_dump / model_validate round-trip preserves all data."""
        eti = EvalTaskInput(
            final_message="answer",
            trace=[{"role": "user", "content": "q"}],
            reference_data={"k": 1},
            task_input="q",
        )
        data = eti.model_dump()
        rebuilt = EvalTaskInput.model_validate(data)
        assert rebuilt == eti

    def test_missing_final_message_raises(self):
        """final_message is required; omitting it raises ValidationError."""
        with pytest.raises(ValidationError, match="final_message"):
            EvalTaskInput()  # type: ignore[call-arg]


# ── Save-time Jinja validation (validate_v2_templates_and_expressions) ───


def _make_v2_eval_config(**kwargs) -> EvalConfig:
    """Helper to build a V2 EvalConfig with minimal ceremony."""
    return EvalConfig(name="V2 Test", config_type=EvalConfigType.v2, **kwargs)


class TestV2TemplateValidation:
    def test_valid_prompt_template(self):
        """A prompt_template with a Jinja expression passes validation."""
        cfg = _make_v2_eval_config(
            properties=LlmJudgeProperties(
                model_name="m",
                model_provider="p",
                prompt_template="Evaluate: {{ final_message }}",
            ),
        )
        assert cfg.properties.prompt_template == "Evaluate: {{ final_message }}"

    def test_invalid_prompt_template_syntax(self):
        """Broken Jinja syntax in prompt_template is rejected."""
        with pytest.raises(ValidationError, match="Invalid Jinja2 template"):
            _make_v2_eval_config(
                properties=LlmJudgeProperties(
                    model_name="m",
                    model_provider="p",
                    prompt_template="Hello {{ broken",
                ),
            )

    def test_static_prompt_template_rejected(self):
        """A prompt_template with no Jinja expressions is rejected."""
        with pytest.raises(ValidationError, match="never references the model output"):
            _make_v2_eval_config(
                properties=LlmJudgeProperties(
                    model_name="m",
                    model_provider="p",
                    prompt_template="Just plain text, nothing dynamic.",
                ),
            )

    def test_comment_only_prompt_template_rejected(self):
        """A prompt_template with only Jinja comments is effectively static and rejected."""
        with pytest.raises(ValidationError, match="never references the model output"):
            _make_v2_eval_config(
                properties=LlmJudgeProperties(
                    model_name="m",
                    model_provider="p",
                    prompt_template="{# This is just a comment #} plain text",
                ),
            )

    def test_reference_data_only_prompt_template_rejected(self):
        """A prompt_template referencing only reference_data is rejected (D30)."""
        with pytest.raises(ValidationError, match="never references the model output"):
            _make_v2_eval_config(
                properties=LlmJudgeProperties(
                    model_name="m",
                    model_provider="p",
                    prompt_template="{{ reference_data.expected_output }}",
                ),
            )

    def test_prompt_template_with_block_passes(self):
        """A prompt_template using {%% blocks referencing model output is not static."""
        cfg = _make_v2_eval_config(
            properties=LlmJudgeProperties(
                model_name="m",
                model_provider="p",
                prompt_template="{% if trace %}has trace{% endif %}",
            ),
        )
        assert cfg is not None

    def test_prompt_template_with_trace_passes(self):
        """A prompt_template referencing trace passes (D30)."""
        cfg = _make_v2_eval_config(
            properties=LlmJudgeProperties(
                model_name="m",
                model_provider="p",
                prompt_template="{{ trace[0].content }}",
            ),
        )
        assert cfg is not None

    def test_prompt_template_with_task_input_passes(self):
        """A prompt_template referencing task_input passes (D30)."""
        cfg = _make_v2_eval_config(
            properties=LlmJudgeProperties(
                model_name="m",
                model_provider="p",
                prompt_template="{{ task_input }}",
            ),
        )
        assert cfg is not None

    def test_valid_value_expression(self):
        """A valid value_expression compiles without error."""
        cfg = _make_v2_eval_config(
            properties=ExactMatchProperties(
                expected_value="yes",
                value_expression="final_message.strip()",
            ),
        )
        assert cfg.properties.value_expression == "final_message.strip()"

    def test_invalid_value_expression(self):
        """Bad Jinja syntax in value_expression is rejected."""
        with pytest.raises(ValidationError, match="Invalid Jinja2 expression"):
            _make_v2_eval_config(
                properties=ExactMatchProperties(
                    expected_value="yes",
                    value_expression="final_message[",
                ),
            )

    def test_none_value_expression_skipped(self):
        """value_expression=None (default) should not be validated."""
        cfg = _make_v2_eval_config(
            properties=ExactMatchProperties(expected_value="yes"),
        )
        assert isinstance(cfg.properties, ExactMatchProperties)
        assert cfg.properties.value_expression is None

    def test_reference_keys_stored(self):
        """reference_keys are stored on LlmJudgeProperties."""
        cfg = _make_v2_eval_config(
            properties=LlmJudgeProperties(
                model_name="m",
                model_provider="p",
                prompt_template="{{ final_message }}",
                reference_keys=["expected_answer", "context"],
            ),
        )
        assert isinstance(cfg.properties, LlmJudgeProperties)
        assert cfg.properties.reference_keys == ["expected_answer", "context"]

    def test_reference_keys_default_empty(self):
        """reference_keys defaults to empty list."""
        cfg = _make_v2_eval_config(
            properties=LlmJudgeProperties(
                model_name="m",
                model_provider="p",
                prompt_template="{{ final_message }}",
            ),
        )
        assert isinstance(cfg.properties, LlmJudgeProperties)
        assert cfg.properties.reference_keys == []

    def test_legacy_config_skips_jinja_validation(self):
        """Legacy (g_eval) configs bypass Jinja validation entirely."""
        cfg = EvalConfig(
            name="Legacy",
            config_type=EvalConfigType.g_eval,
            properties={"eval_steps": ["step1"]},
            model_name="gpt-4",
            model_provider="openai",
        )
        assert cfg.config_type == EvalConfigType.g_eval

    @pytest.mark.parametrize(
        "props",
        [
            PatternMatchProperties(pattern="ok", value_expression="final_message"),
            ContainsProperties(substring="yes", value_expression="final_message"),
            SetCheckProperties(
                expected_set=["a"], value_expression="final_message", mode="equal"
            ),
        ],
        ids=["pattern_match", "contains", "set_check"],
    )
    def test_value_expression_across_property_types(self, props):
        """value_expression validation works for all property types that support it."""
        cfg = _make_v2_eval_config(properties=props)
        assert hasattr(cfg.properties, "value_expression")
        assert cfg.properties.value_expression == "final_message"  # type: ignore[union-attr]


class TestCodeEvalPropertiesValidation:
    VALID_CODE = "def score(output, trace, reference_data, task_input):\n    return {'accuracy': 1.0}\n"

    def test_valid_code(self):
        props = CodeEvalProperties(code=self.VALID_CODE)
        assert props.code == self.VALID_CODE
        assert props.timeout_seconds == 30

    def test_custom_timeout(self):
        props = CodeEvalProperties(code=self.VALID_CODE, timeout_seconds=120)
        assert props.timeout_seconds == 120

    def test_timeout_min_boundary(self):
        with pytest.raises(ValidationError):
            CodeEvalProperties(code=self.VALID_CODE, timeout_seconds=0)

    def test_timeout_max_boundary(self):
        with pytest.raises(ValidationError):
            CodeEvalProperties(code=self.VALID_CODE, timeout_seconds=301)

    def test_syntax_error_rejected(self):
        with pytest.raises(ValidationError, match="syntax error"):
            CodeEvalProperties(code="def score(:\n")

    def test_missing_score_function_rejected(self):
        with pytest.raises(ValidationError, match="module-level 'score' function"):
            CodeEvalProperties(code="def not_score(output):\n    return {}\n")

    def test_code_too_large(self):
        big_code = (
            "def score(output, trace, reference_data, task_input):\n    return {'x': 1.0}\n"
            + ("# padding\n" * 10000)
        )
        if len(big_code.encode("utf-8")) <= 64 * 1024:
            big_code = big_code + " " * (64 * 1024 + 1)
        with pytest.raises(ValidationError, match="too large"):
            CodeEvalProperties(code=big_code)

    def test_nested_score_function_rejected(self):
        code = "def wrapper():\n    def score(output, trace, reference_data, task_input):\n        return {}\n"
        with pytest.raises(ValidationError, match="module-level 'score' function"):
            CodeEvalProperties(code=code)

    def test_async_score_function_accepted(self):
        code = "async def score(output, trace, reference_data, task_input):\n    return {'accuracy': 1.0}\n"
        props = CodeEvalProperties(code=code)
        assert props.code == code


# ── V1 Coexistence Regression Guards ─────────────────────────────────


class TestV1EvalRunCoexistence:
    def test_v1_eval_run_new_optional_fields_default_to_none(self):
        run = EvalRun(
            dataset_id="ds1",
            task_run_config_id="rc1",
            input="What is 2+2?",
            output="4",
            scores={"accuracy": 1.0},
        )
        assert run.eval_input_id is None
        assert run.reference_data is None
        assert run.skipped_reason is None
        assert run.skipped_detail is None

    def test_v1_eval_run_round_trip_preserves_none_defaults(self, mock_task, tmp_path):
        task_path = tmp_path / "task.kiln"
        mock_task.path = task_path
        mock_task.save_to_file()

        eval_obj = Eval(
            name="V1 Compat Eval",
            parent=mock_task,
            eval_set_filter_id="tag::v1set",
            eval_configs_filter_id="tag::golden",
            output_scores=[
                EvalOutputScore(name="acc", type=TaskOutputRatingType.pass_fail)
            ],
        )
        eval_obj.save_to_file()

        config = EvalConfig(
            name="V1 Config",
            parent=eval_obj,
            config_type=EvalConfigType.g_eval,
            model_name="gpt-4",
            model_provider="openai",
            properties={"eval_steps": ["check"]},
        )
        config.save_to_file()

        run = EvalRun(
            parent=config,
            dataset_id="ds1",
            task_run_config_id="rc1",
            input="hello",
            output="world",
            scores={"acc": 0.8},
        )
        run.save_to_file()

        loaded = EvalRun.load_from_file(str(run.path))
        assert loaded.dataset_id == "ds1"
        assert loaded.eval_input_id is None
        assert loaded.reference_data is None
        assert loaded.skipped_reason is None
        assert loaded.skipped_detail is None
        assert loaded.scores == {"acc": 0.8}


class TestV1EvalConfigCoexistence:
    def test_v1_config_with_default_config_type(self):
        config = EvalConfig(
            name="Legacy Default",
            model_name="gpt-4",
            model_provider="openai",
            properties={"eval_steps": ["step1"]},
        )
        assert config.config_type == EvalConfigType.g_eval
        assert isinstance(config.properties, dict)

    def test_v1_config_from_dict_without_config_type_key(self):
        raw = {
            "name": "From Disk V1",
            "model_name": "gpt-4",
            "model_provider": "openai",
            "properties": {"eval_steps": ["step1", "step2"]},
        }
        config = EvalConfig.model_validate(raw)
        assert config.config_type == EvalConfigType.g_eval
        assert isinstance(config.properties, dict)
        assert config.properties["eval_steps"] == ["step1", "step2"]

    def test_v1_properties_with_type_key_not_misrouted(self):
        raw = {
            "name": "Type Key Collision",
            "config_type": "g_eval",
            "model_name": "gpt-4",
            "model_provider": "openai",
            "properties": {
                "eval_steps": ["step1"],
                "type": "exact_match",
            },
        }
        config = EvalConfig.model_validate(raw)
        assert config.config_type == EvalConfigType.g_eval
        assert isinstance(config.properties, dict)
        assert config.properties["type"] == "exact_match"
        assert config.properties["eval_steps"] == ["step1"]

    def test_v1_llm_as_judge_config_type_preserved(self):
        config = EvalConfig(
            name="LLM Judge V1",
            config_type=EvalConfigType.llm_as_judge,
            model_name="gpt-4o",
            model_provider="openai",
            properties={"eval_steps": ["judge it"]},
        )
        assert config.config_type == EvalConfigType.llm_as_judge
        assert isinstance(config.properties, dict)

    def test_v1_config_round_trip_with_type_key_in_properties(
        self, mock_task, tmp_path
    ):
        task_path = tmp_path / "task.kiln"
        mock_task.path = task_path
        mock_task.save_to_file()

        eval_obj = Eval(
            name="Type Key Eval",
            parent=mock_task,
            eval_set_filter_id="tag::s",
            eval_configs_filter_id="tag::g",
            output_scores=[
                EvalOutputScore(name="s", type=TaskOutputRatingType.pass_fail)
            ],
        )
        eval_obj.save_to_file()

        config = EvalConfig(
            name="Type Key Config",
            parent=eval_obj,
            config_type=EvalConfigType.g_eval,
            model_name="gpt-4",
            model_provider="openai",
            properties={
                "eval_steps": ["s1"],
                "type": "some_value",
            },
        )
        config.save_to_file()

        loaded = EvalConfig.load_from_file(str(config.path))
        assert loaded.config_type == EvalConfigType.g_eval
        assert isinstance(loaded.properties, dict)
        assert loaded.properties["type"] == "some_value"
        assert loaded.properties["eval_steps"] == ["s1"]


# ---------------------------------------------------------------------------
# Phase 2: V1 EvalRun output=None guard (Item 1c)
# ---------------------------------------------------------------------------


class TestV1EvalRunOutputNoneGuard:
    """V1 EvalRun with output=None should raise unless skipped."""

    def test_v1_eval_run_output_none_raises(self, mock_task, valid_eval_config_data):
        eval_obj = Eval(
            name="Guard Test",
            parent=mock_task,
            eval_set_filter_id="tag::s",
            eval_configs_filter_id="tag::g",
            output_scores=[
                EvalOutputScore(name="score", type=TaskOutputRatingType.pass_fail)
            ],
        )
        config = EvalConfig(parent=eval_obj, **valid_eval_config_data)

        with pytest.raises(ValueError, match="V1 EvalRun requires output to be set"):
            EvalRun(
                parent=config,
                dataset_id="d1",
                task_run_config_id="c1",
                input="test",
                output=None,
                scores={"score": 1.0},
            )

    def test_v1_eval_run_output_none_skipped_allowed(
        self, mock_task, valid_eval_config_data
    ):
        eval_obj = Eval(
            name="Guard Skipped Test",
            parent=mock_task,
            eval_set_filter_id="tag::s",
            eval_configs_filter_id="tag::g",
            output_scores=[
                EvalOutputScore(name="score", type=TaskOutputRatingType.pass_fail)
            ],
        )
        config = EvalConfig(parent=eval_obj, **valid_eval_config_data)

        run = EvalRun(
            parent=config,
            dataset_id="d1",
            task_run_config_id="c1",
            input="test",
            output=None,
            scores={"score": 1.0},
            skipped_reason="missing_reference_key",
        )
        assert run.output is None
        assert run.skipped_reason == "missing_reference_key"

    def test_v1_eval_run_output_set_passes(self, mock_task, valid_eval_config_data):
        eval_obj = Eval(
            name="Guard Pass Test",
            parent=mock_task,
            eval_set_filter_id="tag::s",
            eval_configs_filter_id="tag::g",
            output_scores=[
                EvalOutputScore(name="score", type=TaskOutputRatingType.pass_fail)
            ],
        )
        config = EvalConfig(parent=eval_obj, **valid_eval_config_data)

        run = EvalRun(
            parent=config,
            dataset_id="d1",
            task_run_config_id="c1",
            input="test",
            output="some output",
            scores={"score": 1.0},
        )
        assert run.output == "some output"

    def test_v2_eval_run_output_none_allowed(self, mock_task):
        eval_obj = Eval(
            name="V2 Guard Test",
            parent=mock_task,
            eval_input_filter_id="tag::s",
            eval_configs_filter_id="tag::g",
            evaluation_data_type=None,
            output_scores=[
                EvalOutputScore(name="score", type=TaskOutputRatingType.pass_fail)
            ],
        )
        config = EvalConfig(
            parent=eval_obj,
            name="V2 Config",
            config_type=EvalConfigType.v2,
            properties=ExactMatchProperties(
                expected_value="gold",
            ),
        )

        run = EvalRun(
            parent=config,
            eval_input_id="e1",
            task_run_config_id="c1",
            input="test",
            output=None,
            scores={"score": 1.0},
            skipped_reason="extraction_failed",
        )
        assert run.output is None


# ---------------------------------------------------------------------------
# Phase 2: CodeEvalProperties dead SyntaxError catch removed (Item 5.4)
# ---------------------------------------------------------------------------


class TestCodeEvalNoDeadSyntaxErrorCatch:
    """After removing the dead except SyntaxError, ast.parse + score fn check still works."""

    def test_valid_code_with_score_fn(self):
        props = CodeEvalProperties(
            code="def score(output, expected):\n    return 1.0\n"
        )
        assert props.code.startswith("def score")

    def test_code_missing_score_fn_raises(self):
        with pytest.raises(
            ValueError, match="must define a module-level 'score' function"
        ):
            CodeEvalProperties(code="def helper():\n    pass\n")

    def test_syntax_error_caught_by_compile(self):
        with pytest.raises(ValueError, match="syntax error"):
            CodeEvalProperties(code="def bad(:\n")

    def test_async_score_fn_valid(self):
        props = CodeEvalProperties(
            code="async def score(output, expected):\n    return 1.0\n"
        )
        assert "async def score" in props.code


class TestValidateScoresAgainstOutputScores:
    """Tests for the shared validate_scores_against_output_scores function."""

    def test_five_star_in_range(self):
        output_scores = [
            EvalOutputScore(name="quality", type=TaskOutputRatingType.five_star)
        ]
        assert (
            validate_scores_against_output_scores({"quality": 3.0}, output_scores) == []
        )
        assert (
            validate_scores_against_output_scores({"quality": 1.0}, output_scores) == []
        )
        assert (
            validate_scores_against_output_scores({"quality": 5.0}, output_scores) == []
        )

    def test_five_star_out_of_range(self):
        output_scores = [
            EvalOutputScore(name="quality", type=TaskOutputRatingType.five_star)
        ]
        problems = validate_scores_against_output_scores(
            {"quality": 6.0}, output_scores
        )
        assert len(problems) == 1
        assert "five_star" in problems[0]
        assert "6.0" in problems[0]

        problems_low = validate_scores_against_output_scores(
            {"quality": 0.5}, output_scores
        )
        assert len(problems_low) == 1
        assert "five_star" in problems_low[0]

    def test_pass_fail_in_range(self):
        output_scores = [
            EvalOutputScore(name="check", type=TaskOutputRatingType.pass_fail)
        ]
        assert (
            validate_scores_against_output_scores({"check": 0.0}, output_scores) == []
        )
        assert (
            validate_scores_against_output_scores({"check": 1.0}, output_scores) == []
        )
        assert (
            validate_scores_against_output_scores({"check": 0.5}, output_scores) == []
        )

    def test_pass_fail_out_of_range(self):
        output_scores = [
            EvalOutputScore(name="check", type=TaskOutputRatingType.pass_fail)
        ]
        problems = validate_scores_against_output_scores({"check": 1.5}, output_scores)
        assert len(problems) == 1
        assert "pass_fail" in problems[0]

        problems_neg = validate_scores_against_output_scores(
            {"check": -0.1}, output_scores
        )
        assert len(problems_neg) == 1

    def test_pass_fail_critical_in_range(self):
        output_scores = [
            EvalOutputScore(name="safety", type=TaskOutputRatingType.pass_fail_critical)
        ]
        assert (
            validate_scores_against_output_scores({"safety": -1.0}, output_scores) == []
        )
        assert (
            validate_scores_against_output_scores({"safety": 0.0}, output_scores) == []
        )
        assert (
            validate_scores_against_output_scores({"safety": 1.0}, output_scores) == []
        )

    def test_pass_fail_critical_out_of_range(self):
        output_scores = [
            EvalOutputScore(name="safety", type=TaskOutputRatingType.pass_fail_critical)
        ]
        problems = validate_scores_against_output_scores(
            {"safety": -1.5}, output_scores
        )
        assert len(problems) == 1
        assert "pass_fail_critical" in problems[0]

        problems_high = validate_scores_against_output_scores(
            {"safety": 1.1}, output_scores
        )
        assert len(problems_high) == 1

    def test_multiple_scores_multiple_errors(self):
        output_scores = [
            EvalOutputScore(name="quality", type=TaskOutputRatingType.five_star),
            EvalOutputScore(name="check", type=TaskOutputRatingType.pass_fail),
        ]
        problems = validate_scores_against_output_scores(
            {"quality": 10.0, "check": 2.0}, output_scores
        )
        assert len(problems) == 2

    def test_missing_score_key_ignored(self):
        output_scores = [
            EvalOutputScore(name="quality", type=TaskOutputRatingType.five_star)
        ]
        assert (
            validate_scores_against_output_scores({"other": 3.0}, output_scores) == []
        )

    def test_non_float_flagged(self):
        output_scores = [
            EvalOutputScore(name="check", type=TaskOutputRatingType.pass_fail)
        ]
        problems = validate_scores_against_output_scores(
            {"check": "not_a_float"}, output_scores
        )
        assert len(problems) == 1

    @pytest.mark.parametrize(
        "score_type",
        [
            TaskOutputRatingType.five_star,
            TaskOutputRatingType.pass_fail,
            TaskOutputRatingType.pass_fail_critical,
            TaskOutputRatingType.custom,
        ],
    )
    @pytest.mark.parametrize(
        "value", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"]
    )
    def test_non_finite_flagged(self, score_type, value):
        """NaN compares False against every range bound, so it passed all
        range checks; pydantic then serialized it as null, making the saved
        EvalRun file fail Dict[str, float] validation on next load."""
        output_scores = [EvalOutputScore(name="metric", type=score_type)]
        problems = validate_scores_against_output_scores(
            {"metric": value}, output_scores
        )
        assert len(problems) == 1

    @pytest.mark.parametrize("value", [12345.6, 0.0, -3.5])
    def test_custom_accepts_any_finite_number(self, value):
        output_scores = [
            EvalOutputScore(name="metric", type=TaskOutputRatingType.custom)
        ]
        assert (
            validate_scores_against_output_scores({"metric": value}, output_scores)
            == []
        )

    def test_integer_scores_accepted(self):
        output_scores = [
            EvalOutputScore(name="quality", type=TaskOutputRatingType.five_star),
            EvalOutputScore(name="check", type=TaskOutputRatingType.pass_fail),
            EvalOutputScore(
                name="safety", type=TaskOutputRatingType.pass_fail_critical
            ),
        ]
        assert (
            validate_scores_against_output_scores({"quality": 3}, output_scores) == []
        )
        assert validate_scores_against_output_scores({"check": 1}, output_scores) == []
        assert (
            validate_scores_against_output_scores({"safety": -1}, output_scores) == []
        )

    def test_boolean_scores_rejected(self):
        output_scores = [
            EvalOutputScore(name="check", type=TaskOutputRatingType.pass_fail)
        ]
        problems = validate_scores_against_output_scores({"check": True}, output_scores)
        assert len(problems) == 1

    def test_empty_scores_returns_empty(self):
        output_scores = [
            EvalOutputScore(name="check", type=TaskOutputRatingType.pass_fail)
        ]
        assert validate_scores_against_output_scores({}, output_scores) == []

    def test_eval_run_validate_scores_still_raises_on_out_of_range(self):
        """Confirm EvalRun.validate_scores still raises ValueError for out-of-range scores,
        ensuring the refactor to use validate_scores_against_output_scores is behavior-preserving."""
        eval_obj = Eval(
            name="Range Check Eval",
            eval_set_filter_id="tag::test",
            eval_configs_filter_id="tag::test2",
            output_scores=[
                EvalOutputScore(name="accuracy", type=TaskOutputRatingType.five_star),
            ],
        )
        eval_config = EvalConfig(
            name="Config",
            config_type=EvalConfigType.v2,
            properties=ExactMatchProperties(expected_value="hello"),
            parent=eval_obj,
        )
        with pytest.raises(
            ValueError,
            match=r"five_star rating and must be a number between 1\.0 and 5\.0",
        ):
            EvalRun(
                eval_input_id="inp1",
                task_run_config_id="rc1",
                eval_config_eval=False,
                input="test",
                output="test",
                scores={"accuracy": 6.0},
                parent=eval_config,
            )


# ---------------------------------------------------------------------------
# V2EvalResult model tests
# ---------------------------------------------------------------------------
class TestV2EvalResult:
    def test_default_construction(self):
        result = V2EvalResult()
        assert result.scores == {}
        assert result.skipped_reason is None
        assert result.skipped_detail is None
        assert result.intermediate_outputs is None

    def test_with_scores(self):
        result = V2EvalResult(scores={"quality": 4.0})
        assert result.scores == {"quality": 4.0}
        assert result.skipped_reason is None

    def test_with_skip(self):
        result = V2EvalResult(
            skipped_reason=SkippedReason.missing_trace,
            skipped_detail="no trace",
        )
        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.missing_trace
        assert result.skipped_detail == "no trace"

    def test_with_intermediate_outputs(self):
        result = V2EvalResult(
            scores={"quality": 5.0},
            intermediate_outputs={"chain_of_thought": "reasoning text"},
        )
        assert result.intermediate_outputs == {"chain_of_thought": "reasoning text"}


# ---------------------------------------------------------------------------
# D27: expected_tools non-empty (ToolCallCheckProperties)
# ---------------------------------------------------------------------------
class TestToolCallCheckExpectedToolsValidator:
    def test_empty_expected_tools_rejected(self):
        with pytest.raises(ValidationError):
            ToolCallCheckProperties(expected_tools=[])

    def test_non_empty_expected_tools_accepted(self):
        props = ToolCallCheckProperties(
            expected_tools=[ToolCallSpec(tool_name="search")]
        )
        assert len(props.expected_tools) == 1


# ---------------------------------------------------------------------------
# D28: ArgMatch regex validation
# ---------------------------------------------------------------------------
class TestArgMatchRegexValidator:
    def test_bad_regex_rejected(self):
        with pytest.raises(ValidationError, match="Invalid regex"):
            ArgMatch(value="[invalid", match_mode="regex")

    def test_valid_regex_accepted(self):
        props = ArgMatch(value=r"^[a-z]+$", match_mode="regex")
        assert props.match_mode == "regex"

    def test_exact_mode_skips_regex_check(self):
        props = ArgMatch(value="[not regex", match_mode="exact")
        assert props.match_mode == "exact"

    def test_contains_mode_skips_regex_check(self):
        props = ArgMatch(value="[not regex", match_mode="contains")
        assert props.match_mode == "contains"


# ---------------------------------------------------------------------------
# D29: reference_key min_length=1
# ---------------------------------------------------------------------------
class TestReferenceKeyMinLength:
    def test_exact_match_empty_reference_key_rejected(self):
        with pytest.raises(ValidationError):
            ExactMatchProperties(reference_key="")

    def test_exact_match_none_reference_key_accepted(self):
        props = ExactMatchProperties(expected_value="val", reference_key=None)
        assert props.reference_key is None

    def test_exact_match_valid_reference_key_accepted(self):
        props = ExactMatchProperties(reference_key="answer")
        assert props.reference_key == "answer"

    def test_contains_empty_reference_key_rejected(self):
        with pytest.raises(ValidationError):
            ContainsProperties(reference_key="")

    def test_contains_none_reference_key_accepted(self):
        props = ContainsProperties(substring="test", reference_key=None)
        assert props.reference_key is None

    def test_set_check_empty_reference_key_rejected(self):
        with pytest.raises(ValidationError):
            SetCheckProperties(reference_key="", mode="subset")

    def test_set_check_none_reference_key_accepted(self):
        props = SetCheckProperties(
            expected_set=["a"], reference_key=None, mode="subset"
        )
        assert props.reference_key is None


# ---------------------------------------------------------------------------
# reference_data_keys — exhaustive per-type accessor
# ---------------------------------------------------------------------------


class TestReferenceDataKeys:
    def test_exact_match_with_reference_key(self):
        props = ExactMatchProperties(reference_key="answer")
        assert reference_data_keys(props) == ["answer"]

    def test_exact_match_without_reference_key(self):
        props = ExactMatchProperties(expected_value="foo")
        assert reference_data_keys(props) == []

    def test_contains_with_reference_key(self):
        props = ContainsProperties(reference_key="expected")
        assert reference_data_keys(props) == ["expected"]

    def test_contains_without_reference_key(self):
        props = ContainsProperties(substring="hi")
        assert reference_data_keys(props) == []

    def test_set_check_with_reference_key(self):
        props = SetCheckProperties(reference_key="items", mode="equal")
        assert reference_data_keys(props) == ["items"]

    def test_set_check_without_reference_key(self):
        props = SetCheckProperties(expected_set=["a"], mode="equal")
        assert reference_data_keys(props) == []

    def test_llm_judge_with_keys(self):
        props = LlmJudgeProperties(
            model_name="gpt-4o",
            model_provider="openai",
            prompt_template="{{ final_message }}",
            reference_keys=["expected_answer", "context"],
        )
        assert reference_data_keys(props) == ["expected_answer", "context"]

    def test_llm_judge_empty_keys(self):
        props = LlmJudgeProperties(
            model_name="gpt-4o",
            model_provider="openai",
            prompt_template="{{ final_message }}",
        )
        assert reference_data_keys(props) == []

    def test_code_eval_with_keys(self):
        code = "def score(output, trace, reference_data, task_input):\n    return {'q': 1.0}"
        props = CodeEvalProperties(code=code, reference_keys=["gold"])
        assert reference_data_keys(props) == ["gold"]

    def test_code_eval_empty_keys(self):
        code = "def score(output, trace, reference_data, task_input):\n    return {'q': 1.0}"
        props = CodeEvalProperties(code=code)
        assert reference_data_keys(props) == []

    def test_pattern_match(self):
        props = PatternMatchProperties(pattern=".*")
        assert reference_data_keys(props) == []

    def test_tool_call_check(self):
        props = ToolCallCheckProperties(
            expected_tools=[ToolCallSpec(tool_name="search")]
        )
        assert reference_data_keys(props) == []

    def test_step_count_check(self):
        props = StepCountCheckProperties(count_type="tool_calls", min_count=1)
        assert reference_data_keys(props) == []

    def test_returns_copy_not_reference(self):
        props = LlmJudgeProperties(
            model_name="gpt-4o",
            model_provider="openai",
            prompt_template="{{ final_message }}",
            reference_keys=["a"],
        )
        result = reference_data_keys(props)
        result.append("mutated")
        assert reference_data_keys(props) == ["a"]


# ---------------------------------------------------------------------------
# eval_reference_data_keys — union across configs
# ---------------------------------------------------------------------------


class TestEvalReferenceDataKeys:
    def _make_eval_with_configs(self, props_list):
        """Build an Eval with V2 configs carrying the given properties."""
        from unittest.mock import Mock

        eval_obj = Mock(spec=Eval)
        configs = []
        for props in props_list:
            cfg = Mock(spec=EvalConfig)
            cfg.config_type = EvalConfigType.v2
            cfg.properties = props
            configs.append(cfg)
        eval_obj.configs = Mock(return_value=configs)
        eval_obj.eval_reference_data_keys = Eval.eval_reference_data_keys.__get__(
            eval_obj, Eval
        )
        return eval_obj

    def test_single_config(self):
        props = ExactMatchProperties(reference_key="answer")
        eval_obj = self._make_eval_with_configs([props])
        assert eval_obj.eval_reference_data_keys() == ["answer"]

    def test_union_across_configs(self):
        p1 = ExactMatchProperties(reference_key="answer")
        p2 = ContainsProperties(reference_key="context")
        p3 = LlmJudgeProperties(
            model_name="gpt-4o",
            model_provider="openai",
            prompt_template="{{ final_message }}",
            reference_keys=["answer", "extra"],
        )
        eval_obj = self._make_eval_with_configs([p1, p2, p3])
        keys = eval_obj.eval_reference_data_keys()
        assert keys == ["answer", "context", "extra"]

    def test_empty_configs(self):
        eval_obj = self._make_eval_with_configs([])
        assert eval_obj.eval_reference_data_keys() == []

    def test_no_reference_data_configs(self):
        props = PatternMatchProperties(pattern=".*")
        eval_obj = self._make_eval_with_configs([props])
        assert eval_obj.eval_reference_data_keys() == []

    def test_dedup_preserves_insertion_order(self):
        p1 = LlmJudgeProperties(
            model_name="gpt-4o",
            model_provider="openai",
            prompt_template="{{ final_message }}",
            reference_keys=["b", "a"],
        )
        p2 = LlmJudgeProperties(
            model_name="gpt-4o",
            model_provider="openai",
            prompt_template="{{ final_message }}",
            reference_keys=["a", "c"],
        )
        eval_obj = self._make_eval_with_configs([p1, p2])
        assert eval_obj.eval_reference_data_keys() == ["b", "a", "c"]
