import zipfile
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
    create_export_directory,
    create_zip,
    export_task,
    get_default_run_config,
    is_dynamic_prompt,
    load_project,
    package_project,
    parse_task_ids,
    print_tasks_table,
    save_prompt_to_task,
    validate_and_build_prompts,
    validate_exported_prompts,
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


class TestCreateExportDirectory:
    def test_creates_directory_with_project(self, temp_project):
        """Test that export directory is created with project.kiln copied."""
        project = temp_project["project"]

        temp_dir, exported_project = create_export_directory(project)

        try:
            assert temp_dir.exists()
            assert (temp_dir / "project.kiln").exists()
            assert exported_project.name == project.name
            assert exported_project.path == temp_dir / "project.kiln"
        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_raises_error_if_project_path_not_set(self):
        """Test that error is raised if project path is not set."""
        project = Project(name="No Path Project")

        with pytest.raises(ValueError, match="Project path is not set"):
            create_export_directory(project)


class TestExportTask:
    def test_exports_task_with_run_config(self, temp_project):
        """Test that task and run config are exported correctly."""
        project = temp_project["project"]
        task = Task.load_from_file(temp_project["task"].path)
        run_config = TaskRunConfig.load_from_file(temp_project["run_config"].path)

        temp_dir, exported_project = create_export_directory(project)

        try:
            exported_task, exported_run_config = export_task(
                task, run_config, exported_project
            )

            assert exported_task.name == task.name
            assert exported_task.instruction == task.instruction
            assert exported_task.id == task.id
            assert exported_task.path is not None
            assert exported_task.path.exists()

            assert exported_run_config.name == run_config.name
            assert exported_run_config.id == run_config.id
            assert exported_run_config.path is not None
            assert exported_run_config.path.exists()

            task_folder = exported_task.path.parent
            assert task_folder.name == temp_project["task"].path.parent.name
        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_preserves_task_folder_name(self, temp_project):
        """Test that the original task folder name is preserved."""
        project = temp_project["project"]
        task = Task.load_from_file(temp_project["task"].path)
        run_config = TaskRunConfig.load_from_file(temp_project["run_config"].path)
        assert task.path is not None
        original_folder_name = task.path.parent.name

        temp_dir, exported_project = create_export_directory(project)

        try:
            exported_task, _ = export_task(task, run_config, exported_project)

            assert exported_task.path is not None
            assert exported_task.path.parent.name == original_folder_name
        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)


class TestSavePromptToTask:
    def test_saves_prompt_and_updates_run_config(self, temp_project):
        """Test that prompt is saved and run config is updated."""
        project = temp_project["project"]
        task = Task.load_from_file(temp_project["task"].path)
        run_config = TaskRunConfig.load_from_file(temp_project["run_config"].path)

        temp_dir, exported_project = create_export_directory(project)

        try:
            exported_task, exported_run_config = export_task(
                task, run_config, exported_project
            )

            prompt = Prompt(
                name="Test Prompt",
                prompt="Test prompt content",
                chain_of_thought_instructions="Think step by step",
            )

            saved_prompt = save_prompt_to_task(
                prompt, exported_task, exported_run_config
            )

            assert saved_prompt.path is not None
            assert saved_prompt.path.exists()
            assert saved_prompt.prompt == "Test prompt content"

            assert exported_run_config.path is not None
            reloaded_run_config = TaskRunConfig.load_from_file(exported_run_config.path)
            assert (
                reloaded_run_config.run_config_properties.prompt_id
                == f"id::{saved_prompt.id}"
            )

            assert exported_task.path is not None
            exported_task_reloaded = Task.load_from_file(exported_task.path)
            prompts = exported_task_reloaded.prompts()
            assert len(prompts) == 1
            assert prompts[0].id == saved_prompt.id
        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)


class TestValidateExportedPrompts:
    def test_validates_matching_prompts(self, temp_project):
        """Test that validation passes when prompts match."""
        project = temp_project["project"]
        task = Task.load_from_file(temp_project["task"].path)
        run_config = TaskRunConfig.load_from_file(temp_project["run_config"].path)

        temp_dir, exported_project = create_export_directory(project)

        try:
            exported_task, exported_run_config = export_task(
                task, run_config, exported_project
            )

            original_prompt = Prompt(
                name="Test Prompt",
                prompt="Test prompt content",
                chain_of_thought_instructions=None,
            )

            save_prompt_to_task(original_prompt, exported_task, exported_run_config)

            assert task.id is not None
            validate_exported_prompts(
                {task.id: original_prompt},
                {task.id: exported_task},
                {task.id: exported_run_config},
            )
        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_raises_error_on_prompt_mismatch(self, temp_project):
        """Test that validation fails when prompts don't match."""
        project = temp_project["project"]
        task = Task.load_from_file(temp_project["task"].path)
        run_config = TaskRunConfig.load_from_file(temp_project["run_config"].path)

        temp_dir, exported_project = create_export_directory(project)

        try:
            exported_task, exported_run_config = export_task(
                task, run_config, exported_project
            )

            original_prompt = Prompt(
                name="Test Prompt",
                prompt="Original prompt content",
                chain_of_thought_instructions=None,
            )

            different_prompt = Prompt(
                name="Test Prompt",
                prompt="Different prompt content",
                chain_of_thought_instructions=None,
                parent=exported_task,
            )
            different_prompt.save_to_file()

            exported_run_config.run_config_properties.prompt_id = (
                f"id::{different_prompt.id}"
            )
            exported_run_config.save_to_file()

            assert task.id is not None
            with pytest.raises(ValueError, match="Prompt mismatch"):
                validate_exported_prompts(
                    {task.id: original_prompt},
                    {task.id: exported_task},
                    {task.id: exported_run_config},
                )
        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)


class TestCreateZip:
    def test_creates_valid_zip_file(self, tmp_path: Path):
        """Test that a valid zip file is created."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("content1")
        (source_dir / "subdir").mkdir()
        (source_dir / "subdir" / "file2.txt").write_text("content2")

        output_path = tmp_path / "output.zip"

        create_zip(source_dir, output_path)

        assert output_path.exists()

        with zipfile.ZipFile(output_path, "r") as zipf:
            names = zipf.namelist()
            assert "file1.txt" in names
            assert "subdir/file2.txt" in names

            assert zipf.read("file1.txt").decode() == "content1"
            assert zipf.read("subdir/file2.txt").decode() == "content2"

    def test_creates_parent_directories(self, tmp_path: Path):
        """Test that parent directories are created for output path."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("content")

        output_path = tmp_path / "nested" / "dirs" / "output.zip"

        create_zip(source_dir, output_path)

        assert output_path.exists()


class TestPackageProjectEndToEnd:
    def test_creates_zip_with_correct_structure(self, temp_project, tmp_path: Path):
        """Test full end-to-end export creates correct zip structure."""
        output_path = tmp_path / "export" / "output.zip"

        package_project(
            project_path=temp_project["path"],
            tasks=temp_project["task"].id,
            all_tasks=False,
            output=output_path,
        )

        assert output_path.exists()

        with zipfile.ZipFile(output_path, "r") as zipf:
            names = zipf.namelist()

            assert "project.kiln" in names

            task_files = [
                n for n in names if n.startswith("tasks/") and n.endswith("task.kiln")
            ]
            assert len(task_files) == 1

            run_config_files = [
                n for n in names if "run_configs" in n and n.endswith(".kiln")
            ]
            assert len(run_config_files) == 1

            prompt_files = [n for n in names if "prompts" in n and n.endswith(".kiln")]
            assert len(prompt_files) == 1

    def test_exported_project_is_loadable(self, temp_project, tmp_path: Path):
        """Test that the exported project can be loaded and used."""
        output_path = tmp_path / "output.zip"
        extract_path = tmp_path / "extracted"

        package_project(
            project_path=temp_project["path"],
            tasks=temp_project["task"].id,
            all_tasks=False,
            output=output_path,
        )

        with zipfile.ZipFile(output_path, "r") as zipf:
            zipf.extractall(extract_path)

        loaded_project = Project.load_from_file(extract_path / "project.kiln")
        assert loaded_project.name == temp_project["project"].name

        tasks = loaded_project.tasks()
        assert len(tasks) == 1
        assert tasks[0].id == temp_project["task"].id

        prompts = tasks[0].prompts()
        assert len(prompts) == 1

        run_configs = tasks[0].run_configs()
        assert len(run_configs) == 1
        assert run_configs[0].run_config_properties.prompt_id == f"id::{prompts[0].id}"

    def test_exports_multiple_tasks(
        self, temp_project_with_multiple_tasks, tmp_path: Path
    ):
        """Test exporting multiple tasks."""
        output_path = tmp_path / "output.zip"

        package_project(
            project_path=temp_project_with_multiple_tasks["path"],
            tasks="",
            all_tasks=True,
            output=output_path,
        )

        assert output_path.exists()

        extract_path = tmp_path / "extracted"
        with zipfile.ZipFile(output_path, "r") as zipf:
            zipf.extractall(extract_path)

        loaded_project = Project.load_from_file(extract_path / "project.kiln")
        tasks = loaded_project.tasks()
        assert len(tasks) == 3

        for task in tasks:
            prompts = task.prompts()
            assert len(prompts) == 1
            run_configs = task.run_configs()
            assert len(run_configs) == 1
