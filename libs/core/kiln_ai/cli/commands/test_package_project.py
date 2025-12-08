from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
from kiln_ai.datamodel.prompt import Prompt
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import RunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.task import TaskRunConfig

from .package_project import (
    build_prompt_from_builder,
    check_for_tools,
    get_default_run_config,
    is_dynamic_prompt,
    load_project,
    package_project,
    parse_task_ids,
    print_tasks_table,
    validate_and_build_prompts,
    validate_tasks,
)


@pytest.fixture
def temp_project(tmp_path: Path):
    """Create a temporary project with tasks and run configs for testing."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction for the task",
        parent=project,
    )
    task.save_to_file()

    run_config = TaskRunConfig(
        name="Test Run Config",
        parent=task,
        run_config_properties=RunConfigProperties(
            model_name="gpt-4o",
            model_provider_name="openai",
            prompt_id=PromptGenerators.SIMPLE.value,
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    run_config.save_to_file()

    task.default_run_config_id = run_config.id
    task.save_to_file()

    return {
        "project": project,
        "task": task,
        "run_config": run_config,
        "path": tmp_path,
    }


@pytest.fixture
def temp_project_with_multiple_tasks(tmp_path: Path):
    """Create a project with multiple tasks for testing."""
    project = Project(name="Multi Task Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    tasks = []
    run_configs = []
    for i in range(3):
        task = Task(
            name=f"Task {i + 1}",
            instruction=f"Instruction for task {i + 1}",
            parent=project,
        )
        task.save_to_file()

        run_config = TaskRunConfig(
            name=f"Run Config {i + 1}",
            parent=task,
            run_config_properties=RunConfigProperties(
                model_name="gpt-4o",
                model_provider_name="openai",
                prompt_id=PromptGenerators.SIMPLE.value,
                structured_output_mode=StructuredOutputMode.default,
            ),
        )
        run_config.save_to_file()

        task.default_run_config_id = run_config.id
        task.save_to_file()

        tasks.append(task)
        run_configs.append(run_config)

    return {
        "project": project,
        "tasks": tasks,
        "run_configs": run_configs,
        "path": tmp_path,
    }


@pytest.fixture
def temp_project_no_run_config(tmp_path: Path):
    """Create a project with a task that has no default run config."""
    project = Project(name="No Config Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Task Without Config",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    return {"project": project, "task": task, "path": tmp_path}


@pytest.fixture
def temp_project_with_tools(tmp_path: Path):
    """Create a project with a run config that uses tools."""
    project = Project(name="Tools Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Task With Tools",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    run_config = TaskRunConfig(
        name="Config With Tools",
        parent=task,
        run_config_properties=RunConfigProperties(
            model_name="gpt-4o",
            model_provider_name="openai",
            prompt_id=PromptGenerators.SIMPLE.value,
            structured_output_mode=StructuredOutputMode.default,
            tools_config=ToolsRunConfig(tools=["kiln_tool::add_numbers"]),
        ),
    )
    run_config.save_to_file()

    task.default_run_config_id = run_config.id
    task.save_to_file()

    return {
        "project": project,
        "task": task,
        "run_config": run_config,
        "path": tmp_path,
    }


@pytest.fixture
def temp_project_with_dynamic_prompt(tmp_path: Path):
    """Create a project with a dynamic prompt generator."""
    project = Project(name="Dynamic Prompt Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Task With Dynamic Prompt",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    run_config = TaskRunConfig(
        name="Config With Dynamic Prompt",
        parent=task,
        run_config_properties=RunConfigProperties(
            model_name="gpt-4o",
            model_provider_name="openai",
            prompt_id=PromptGenerators.FEW_SHOT.value,
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    run_config.save_to_file()

    task.default_run_config_id = run_config.id
    task.save_to_file()

    return {
        "project": project,
        "task": task,
        "run_config": run_config,
        "path": tmp_path,
    }


class TestLoadProject:
    def test_load_project_from_file(self, temp_project):
        """Test loading a project from a direct file path."""
        project_file = temp_project["path"] / "project.kiln"
        loaded = load_project(project_file)
        assert loaded.name == "Test Project"

    def test_load_project_from_folder(self, temp_project):
        """Test loading a project from a folder containing project.kiln."""
        loaded = load_project(temp_project["path"])
        assert loaded.name == "Test Project"

    def test_load_project_missing_file(self, tmp_path: Path):
        """Test error when project file doesn't exist."""
        with pytest.raises(typer.Exit) as exc_info:
            load_project(tmp_path / "nonexistent.kiln")
        assert exc_info.value.exit_code == 1

    def test_load_project_missing_folder(self, tmp_path: Path):
        """Test error when folder has no project.kiln."""
        empty_folder = tmp_path / "empty"
        empty_folder.mkdir()
        with pytest.raises(typer.Exit) as exc_info:
            load_project(empty_folder)
        assert exc_info.value.exit_code == 1


class TestParseTaskIds:
    def test_parse_all_tasks_flag(self, temp_project_with_multiple_tasks):
        """Test parsing with --all-tasks flag."""
        tasks = temp_project_with_multiple_tasks["tasks"]
        result = parse_task_ids("", True, tasks)
        assert len(result) == 3

    def test_parse_all_string(self, temp_project_with_multiple_tasks):
        """Test parsing with 'all' string."""
        tasks = temp_project_with_multiple_tasks["tasks"]
        result = parse_task_ids("all", False, tasks)
        assert len(result) == 3

    def test_parse_comma_separated(self, temp_project_with_multiple_tasks):
        """Test parsing comma-separated task IDs."""
        tasks = temp_project_with_multiple_tasks["tasks"]
        task_ids = f"{tasks[0].id},{tasks[1].id}"
        result = parse_task_ids(task_ids, False, tasks)
        assert len(result) == 2
        assert tasks[0].id in result
        assert tasks[1].id in result

    def test_parse_single_task(self, temp_project_with_multiple_tasks):
        """Test parsing a single task ID."""
        tasks = temp_project_with_multiple_tasks["tasks"]
        result = parse_task_ids(tasks[0].id, False, tasks)
        assert result == [tasks[0].id]

    def test_parse_no_tasks_error(self, temp_project_with_multiple_tasks):
        """Test error when no tasks specified."""
        tasks = temp_project_with_multiple_tasks["tasks"]
        with pytest.raises(typer.Exit) as exc_info:
            parse_task_ids("", False, tasks)
        assert exc_info.value.exit_code == 1


class TestValidateTasks:
    def test_validate_existing_tasks(self, temp_project_with_multiple_tasks):
        """Test validation of existing task IDs."""
        project = temp_project_with_multiple_tasks["project"]
        tasks = temp_project_with_multiple_tasks["tasks"]
        task_ids = [tasks[0].id, tasks[1].id]

        result = validate_tasks(task_ids, project)
        assert len(result) == 2

    def test_validate_missing_task(self, temp_project_with_multiple_tasks):
        """Test error when task ID doesn't exist."""
        project = temp_project_with_multiple_tasks["project"]
        with pytest.raises(typer.Exit) as exc_info:
            validate_tasks(["nonexistent_id"], project)
        assert exc_info.value.exit_code == 1


class TestGetDefaultRunConfig:
    def test_get_valid_run_config(self, temp_project):
        """Test getting a valid default run config."""
        task = temp_project["task"]
        task_reloaded = Task.load_from_file(task.path)
        result = get_default_run_config(task_reloaded)
        assert result.name == "Test Run Config"

    def test_get_run_config_not_set(self, temp_project_no_run_config):
        """Test error when no default run config is set."""
        task = temp_project_no_run_config["task"]
        with pytest.raises(typer.Exit) as exc_info:
            get_default_run_config(task)
        assert exc_info.value.exit_code == 1

    def test_get_run_config_id_invalid(self, temp_project):
        """Test error when default run config ID doesn't exist."""
        task = temp_project["task"]
        task_reloaded = Task.load_from_file(task.path)
        task_reloaded.default_run_config_id = "nonexistent_id"

        with pytest.raises(typer.Exit) as exc_info:
            get_default_run_config(task_reloaded)
        assert exc_info.value.exit_code == 1


class TestCheckForTools:
    def test_no_tools_passes(self, temp_project):
        """Test that run config without tools passes."""
        task = temp_project["task"]
        run_config = temp_project["run_config"]
        check_for_tools(run_config, task)

    def test_with_tools_fails(self, temp_project_with_tools):
        """Test that run config with tools fails."""
        task = temp_project_with_tools["task"]
        run_config = temp_project_with_tools["run_config"]

        with pytest.raises(typer.Exit) as exc_info:
            check_for_tools(run_config, task)
        assert exc_info.value.exit_code == 1


class TestIsDynamicPrompt:
    @pytest.mark.parametrize(
        "prompt_id,expected",
        [
            (PromptGenerators.SIMPLE.value, False),
            (PromptGenerators.SHORT.value, False),
            (PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT.value, False),
            (PromptGenerators.FEW_SHOT.value, True),
            (PromptGenerators.MULTI_SHOT.value, True),
            (PromptGenerators.REPAIRS.value, True),
            (PromptGenerators.FEW_SHOT_CHAIN_OF_THOUGHT.value, True),
            (PromptGenerators.MULTI_SHOT_CHAIN_OF_THOUGHT.value, True),
            ("id::some_saved_prompt", False),
        ],
    )
    def test_is_dynamic_prompt(self, prompt_id, expected):
        """Test dynamic prompt detection."""
        assert is_dynamic_prompt(prompt_id) == expected


class TestValidateAndBuildPrompts:
    def test_build_static_prompts(self, temp_project):
        """Test building prompts with static generators."""
        task = Task.load_from_file(temp_project["task"].path)
        run_config = TaskRunConfig.load_from_file(temp_project["run_config"].path)

        result = validate_and_build_prompts([task], {task.id: run_config})

        assert task.id in result
        assert isinstance(result[task.id], Prompt)
        assert "Test instruction" in result[task.id].prompt

    def test_build_dynamic_prompts_confirm_yes(self, temp_project_with_dynamic_prompt):
        """Test building prompts with dynamic generators when user confirms."""
        task = Task.load_from_file(temp_project_with_dynamic_prompt["task"].path)
        run_config = TaskRunConfig.load_from_file(
            temp_project_with_dynamic_prompt["run_config"].path
        )

        with patch(
            "kiln_ai.cli.commands.package_project.typer.confirm", return_value=True
        ):
            result = validate_and_build_prompts([task], {task.id: run_config})

        assert task.id in result
        assert isinstance(result[task.id], Prompt)

    def test_build_dynamic_prompts_confirm_no(self, temp_project_with_dynamic_prompt):
        """Test that user can decline dynamic prompt export."""
        task = Task.load_from_file(temp_project_with_dynamic_prompt["task"].path)
        run_config = TaskRunConfig.load_from_file(
            temp_project_with_dynamic_prompt["run_config"].path
        )

        with patch(
            "kiln_ai.cli.commands.package_project.typer.confirm", return_value=False
        ):
            with pytest.raises(typer.Exit) as exc_info:
                validate_and_build_prompts([task], {task.id: run_config})
            assert exc_info.value.exit_code == 0


class TestPackageProjectCommand:
    def test_full_validation_flow(self, temp_project):
        """Test the complete validation flow."""
        result = package_project(
            project_path=temp_project["path"],
            tasks=temp_project["task"].id,
            all_tasks=False,
            output=Path("./test_output.zip"),
        )

        assert len(result) == 1
        task_id = temp_project["task"].id
        assert task_id in result
        assert isinstance(result[task_id], Prompt)

    def test_all_tasks_flow(self, temp_project_with_multiple_tasks):
        """Test validation with all tasks."""
        result = package_project(
            project_path=temp_project_with_multiple_tasks["path"],
            tasks="",
            all_tasks=True,
            output=Path("./test_output.zip"),
        )

        assert len(result) == 3

    def test_missing_project_path_error(self):
        """Test error when no project path is provided."""
        with pytest.raises(typer.Exit) as exc_info:
            package_project(
                project_path=None,
                tasks="123",
                all_tasks=False,
                output=Path("./test_output.zip"),
            )
        assert exc_info.value.exit_code == 1

    def test_missing_project_error(self, tmp_path: Path):
        """Test error handling for missing project."""
        with pytest.raises(typer.Exit) as exc_info:
            package_project(
                project_path=tmp_path / "nonexistent",
                tasks="123",
                all_tasks=False,
                output=Path("./test_output.zip"),
            )
        assert exc_info.value.exit_code == 1

    def test_no_tasks_error(self, temp_project):
        """Test error when no tasks are specified."""
        with pytest.raises(typer.Exit) as exc_info:
            package_project(
                project_path=temp_project["path"],
                tasks="",
                all_tasks=False,
                output=Path("./test_output.zip"),
            )
        assert exc_info.value.exit_code == 1


class TestPrintTasksTable:
    def test_prints_without_error(self, temp_project_with_multiple_tasks, capsys):
        """Test that print_tasks_table runs without errors."""
        tasks = temp_project_with_multiple_tasks["tasks"]
        print_tasks_table(tasks)


class TestBuildPromptFromBuilder:
    def test_builds_prompt_model(self, temp_project):
        """Test building a Prompt model from a builder."""
        from kiln_ai.adapters.prompt_builders import SimplePromptBuilder

        task = Task.load_from_file(temp_project["task"].path)
        builder = SimplePromptBuilder(task)

        result = build_prompt_from_builder(builder)

        assert isinstance(result, Prompt)
        assert result.name == "Exported Prompt"
        assert "Test instruction" in result.prompt
