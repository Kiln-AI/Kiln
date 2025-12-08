import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from kiln_ai.adapters.prompt_builders import BasePromptBuilder, prompt_builder_from_id
from kiln_ai.cli.commands.projects import print_projects_table
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.prompt import Prompt
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.task import TaskRunConfig

console = Console()

# Dynamic prompt generators that require user confirmation
DYNAMIC_PROMPT_GENERATORS = {
    PromptGenerators.MULTI_SHOT.value,
    PromptGenerators.FEW_SHOT.value,
    PromptGenerators.REPAIRS.value,
    PromptGenerators.FEW_SHOT_CHAIN_OF_THOUGHT.value,
    PromptGenerators.MULTI_SHOT_CHAIN_OF_THOUGHT.value,
}


def load_project(project_path: Path) -> Project:
    """Load a project from a path, handling both folder and direct file paths."""
    if project_path.is_dir():
        project_file = project_path / "project.kiln"
        if not project_file.exists():
            print_projects_table(title="Available Projects")
            console.print(
                f"\n[red]Error:[/red] No project.kiln file found in {project_path}\nYou must provide this argument (see list above for available projects).\n"
            )
            raise typer.Exit(1)
        project_path = project_file

    if not project_path.exists():
        print_projects_table(title="Available Projects")
        console.print(
            f"\n[red]Error:[/red] Project file not found: {project_path}\nYou must provide this argument (see list above for available projects).\n"
        )
        raise typer.Exit(1)

    try:
        return Project.load_from_file(project_path)
    except Exception as e:
        print_projects_table(title="Available Projects")
        console.print(
            f"\n[red]Error:[/red] Failed to load project: {e}\nYou must provide this argument (see list above for available projects).\n"
        )
        raise typer.Exit(1)


def print_tasks_table(tasks: list[Task], title: str = "Available Tasks") -> None:
    """Print a table of tasks with their IDs and names."""
    table = Table(title=title)
    table.add_column("Task ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="white")

    for task in tasks:
        table.add_row(task.id or "N/A", task.name)

    console.print(table)


def parse_task_ids(
    tasks_arg: str, all_tasks_flag: bool, available_tasks: list[Task]
) -> list[str]:
    """Parse and validate task IDs from CLI arguments."""
    if all_tasks_flag or tasks_arg.lower() == "all":
        return [task.id for task in available_tasks if task.id]

    if not tasks_arg:
        print_tasks_table(available_tasks)
        console.print(
            "\n[red]Error:[/red] No tasks specified.\nYou must provide a list of task IDs via --task/-t or pass --all-tasks\nSee list above for available tasks.\n"
        )
        raise typer.Exit(1)

    return [tid.strip() for tid in tasks_arg.split(",") if tid.strip()]


def validate_tasks(task_ids: list[str], project: Project) -> list[Task]:
    """Validate that all requested task IDs exist in the project."""
    available_tasks = project.tasks()
    task_id_to_task = {task.id: task for task in available_tasks if task.id}

    missing_ids = [tid for tid in task_ids if tid not in task_id_to_task]
    if missing_ids:
        console.print(
            f"[red]Error:[/red] Task ID(s) not found: {', '.join(missing_ids)}"
        )
        print_tasks_table(available_tasks)
        raise typer.Exit(1)

    return [task_id_to_task[tid] for tid in task_ids]


def get_default_run_config(task: Task) -> TaskRunConfig:
    """Get and validate the default run config for a task."""
    if not task.default_run_config_id:
        console.print(
            f"[red]Error:[/red] Task '{task.name}' (ID: {task.id}) has no default run config set."
        )
        console.print(
            "\n[dim]Hint: Set a default run config in the Kiln app UI before exporting.[/dim]"
        )
        raise typer.Exit(1)

    run_configs = task.run_configs()
    run_config = next(
        (rc for rc in run_configs if rc.id == task.default_run_config_id), None
    )

    if not run_config:
        console.print(
            f"[red]Error:[/red] Default run config '{task.default_run_config_id}' not found for task '{task.name}'."
        )
        console.print(
            "\n[dim]Hint: The run config may have been deleted. Set a new default in the Kiln app UI.[/dim]"
        )
        raise typer.Exit(1)

    return run_config


def check_for_tools(run_config: TaskRunConfig, task: Task) -> None:
    """Check if the run config uses tools and warn the user."""
    if (
        run_config.run_config_properties.tools_config
        and run_config.run_config_properties.tools_config.tools
    ):
        console.print(
            f"[yellow]Warning:[/yellow] Task '{task.name}' uses tools in its default run config."
        )
        console.print(
            "[red]Error:[/red] Tools are not currently supported in exported projects."
        )
        raise typer.Exit(1)


def is_dynamic_prompt(prompt_id: str) -> bool:
    """Check if a prompt ID refers to a dynamic prompt generator."""
    return prompt_id in DYNAMIC_PROMPT_GENERATORS


def build_prompt_from_builder(builder: BasePromptBuilder) -> Prompt:
    """Build a Prompt model from a prompt builder."""
    prompt_text = builder.build_prompt(include_json_instructions=False)
    cot_prompt = builder.chain_of_thought_prompt()

    return Prompt(
        name="Exported Prompt",
        prompt=prompt_text,
        chain_of_thought_instructions=cot_prompt,
        generator_id=builder.prompt_id(),
    )


def validate_and_build_prompts(
    tasks: list[Task], run_configs: dict[str, TaskRunConfig]
) -> dict[str, Prompt]:
    """Validate prompts and build Prompt objects for each task."""
    task_prompts: dict[str, Prompt] = {}
    has_dynamic_prompts = False

    # First pass: check for dynamic prompts
    for task in tasks:
        run_config = run_configs[task.id]  # type: ignore
        prompt_id = run_config.run_config_properties.prompt_id

        if is_dynamic_prompt(prompt_id):
            has_dynamic_prompts = True
            console.print(
                f"[yellow]Warning:[/yellow] Task '{task.name}' uses dynamic prompt generator: {prompt_id}"
            )

    # Ask for confirmation if any dynamic prompts
    if has_dynamic_prompts:
        console.print(
            "\n[yellow]You have a dynamic prompt generator selected.[/yellow] "
            "In Kiln this will dynamically build a prompt, using few-shot examples from your dataset. "
            "We can build the prompt and save it for the export, but due to its dynamic nature it won't be static. "
            "We suggest creating a default run config based on a static prompt for better consistency."
        )
        if not typer.confirm("\nContinue anyways?"):
            raise typer.Exit(0)

    # Second pass: build prompts
    for task in tasks:
        run_config = run_configs[task.id]  # type: ignore
        prompt_id = run_config.run_config_properties.prompt_id

        try:
            builder = prompt_builder_from_id(prompt_id, task)
            prompt = build_prompt_from_builder(builder)
            task_prompts[task.id] = prompt  # type: ignore
        except Exception as e:
            console.print(
                f"[red]Error:[/red] Failed to build prompt for task '{task.name}': {e}"
            )
            raise typer.Exit(1)

    return task_prompts


def create_export_directory(project: Project) -> tuple[Path, Project]:
    """Create a temporary export directory and copy project.kiln into it.

    Returns:
        Tuple of (temp_dir_path, exported_project)
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="kiln_export_"))

    if project.path is None:
        raise ValueError("Project path is not set")

    shutil.copy(project.path, temp_dir / "project.kiln")
    exported_project = Project.load_from_file(temp_dir / "project.kiln")

    return temp_dir, exported_project


def export_task(
    task: Task, run_config: TaskRunConfig, exported_project: Project
) -> tuple[Task, TaskRunConfig]:
    """Copy a task and its default run config to the export directory.

    Returns:
        Tuple of (exported_task, exported_run_config)
    """
    if task.path is None:
        raise ValueError(f"Task '{task.name}' path is not set")
    if run_config.path is None:
        raise ValueError(f"Run config '{run_config.name}' path is not set")
    if exported_project.path is None:
        raise ValueError("Exported project path is not set")

    task_folder_name = task.path.parent.name
    run_config_folder_name = run_config.path.parent.name

    task_dir = exported_project.path.parent / "tasks" / task_folder_name
    task_dir.mkdir(parents=True, exist_ok=True)
    exported_task_path = task_dir / "task.kiln"
    shutil.copy(task.path, exported_task_path)

    exported_task = Task.load_from_file(exported_task_path)
    exported_task.parent = exported_project

    run_config_dir = task_dir / "run_configs" / run_config_folder_name
    run_config_dir.mkdir(parents=True, exist_ok=True)
    exported_run_config_path = run_config_dir / "task_run_config.kiln"
    shutil.copy(run_config.path, exported_run_config_path)

    exported_run_config = TaskRunConfig.load_from_file(exported_run_config_path)
    exported_run_config.parent = exported_task

    return exported_task, exported_run_config


def save_prompt_to_task(
    prompt: Prompt, exported_task: Task, exported_run_config: TaskRunConfig
) -> Prompt:
    """Save a prompt to the exported task and update the run config to reference it.

    Returns:
        The saved prompt
    """
    prompt = prompt.model_copy(deep=True)
    prompt.parent = exported_task
    prompt.save_to_file()

    # check it saved to the correct location
    saved = False
    for exported_task_prompt in exported_task.prompts(readonly=True):
        if (
            exported_task_prompt.path == prompt.path
            and exported_task_prompt.id == prompt.id
        ):
            saved = True
            break
    if not saved:
        raise ValueError(
            f"Prompt saved to incorrect location: {prompt.path} != {exported_task_prompt.path}"
        )

    exported_run_config.run_config_properties.prompt_id = f"id::{prompt.id}"
    exported_run_config.save_to_file()

    return prompt


def validate_exported_prompts(
    original_prompts: dict[str, Prompt],
    exported_tasks: dict[str, Task],
    exported_run_configs: dict[str, TaskRunConfig],
) -> None:
    """Validate that exported prompts match the originals."""
    for task_id, original_prompt in original_prompts.items():
        exported_task = exported_tasks[task_id]
        exported_run_config = exported_run_configs[task_id]

        exported_prompts_list = exported_task.prompts()
        if not exported_prompts_list:
            raise ValueError(
                f"No prompts found for exported task '{exported_task.name}'"
            )

        rebuilt_prompts = validate_and_build_prompts(
            [exported_task], {task_id: exported_run_config}
        )
        rebuilt_prompt = rebuilt_prompts[task_id]

        if rebuilt_prompt.prompt != original_prompt.prompt:
            raise ValueError(
                f"Prompt mismatch for task '{exported_task.name}': "
                f"exported prompt does not match original"
            )

        if (
            rebuilt_prompt.chain_of_thought_instructions
            != original_prompt.chain_of_thought_instructions
        ):
            raise ValueError(
                f"Chain of thought mismatch for task '{exported_task.name}': "
                f"exported prompt does not match original"
            )


def create_zip(source_dir: Path, output_path: Path) -> None:
    """Create a zip file from the source directory contents."""
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir)
                zipf.write(file_path, arcname)


def package_project(
    project_path: Annotated[
        Path | None,
        typer.Argument(help="Path to project.kiln file or folder containing it"),
    ] = None,
    tasks: Annotated[
        str,
        typer.Option(
            "-t", "--task", "--tasks", help="Comma-separated task IDs or 'all'"
        ),
    ] = "",
    all_tasks: Annotated[
        bool, typer.Option("--all-tasks", help="Export all tasks in the project")
    ] = False,
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Output path for the zip file")
    ] = Path("./exported_kiln_project.zip"),
) -> dict[str, Prompt]:
    """Package a Kiln project for deployment.

    Creates a minimal version of a Kiln project containing only the files needed
    to run specified tasks on a server.
    """
    # Stage 1: Validation

    # 1. Load and validate project
    if project_path is None:
        print_projects_table(title="Available Projects")
        console.print(
            "\n[red]Error:[/red] No project path provided. You must provide this argument (see list above for available projects).\n"
        )
        raise typer.Exit(1)

    console.print(f"Loading project from {project_path}...")
    project = load_project(project_path)
    console.print(f"[green]✓[/green] Loaded project: {project.name}")

    # 2. Parse and validate task IDs
    available_tasks = project.tasks()
    if not available_tasks:
        console.print("[red]Error:[/red] Project has no tasks.")
        raise typer.Exit(1)

    task_ids = parse_task_ids(tasks, all_tasks, available_tasks)
    validated_tasks = validate_tasks(task_ids, project)
    console.print(
        f"[green]✓[/green] Validated {len(validated_tasks)} task(s): {', '.join(t.name for t in validated_tasks)}"
    )

    # 3. Validate run configs and check for tools
    run_configs: dict[str, TaskRunConfig] = {}
    for task in validated_tasks:
        run_config = get_default_run_config(task)
        check_for_tools(run_config, task)
        run_configs[task.id] = run_config  # type: ignore

    console.print("[green]✓[/green] Validated default run configs")

    # 4. Build and validate prompts
    task_prompts = validate_and_build_prompts(validated_tasks, run_configs)
    console.print("[green]✓[/green] Built and validated prompts")

    console.print("\n[green]Validation complete![/green]")

    # Stage 2: Copy and Zip

    console.print("\n[bold]Exporting project...[/bold]")

    # 1. Create export directory with project.kiln
    temp_dir, exported_project = create_export_directory(project)
    console.print("[green]✓[/green] Created export directory")

    try:
        # 2. Export tasks and run configs
        exported_tasks: dict[str, Task] = {}
        exported_run_configs: dict[str, TaskRunConfig] = {}

        for task in validated_tasks:
            run_config = run_configs[task.id]  # type: ignore
            exported_task, exported_run_config = export_task(
                task, run_config, exported_project
            )
            exported_tasks[task.id] = exported_task  # type: ignore
            exported_run_configs[task.id] = exported_run_config  # type: ignore

        console.print(f"[green]✓[/green] Exported {len(validated_tasks)} task(s)")

        # 3. Save prompts to exported tasks
        for task in validated_tasks:
            prompt = task_prompts[task.id]  # type: ignore
            exported_task = exported_tasks[task.id]  # type: ignore
            exported_run_config = exported_run_configs[task.id]  # type: ignore
            save_prompt_to_task(prompt, exported_task, exported_run_config)

        console.print("[green]✓[/green] Saved prompts to exported tasks")

        # 4. Validate exported prompts match originals
        validate_exported_prompts(task_prompts, exported_tasks, exported_run_configs)
        console.print("[green]✓[/green] Validated exported prompts")

        # 5. Create zip file
        create_zip(temp_dir, output)
        console.print(f"[green]✓[/green] Created zip file: {output}")

    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Final success message
    console.print(
        f"\n[bold green]Success![/bold green] Your project has been packaged and saved to:\n"
        f"  [cyan]{output.resolve()}[/cyan]\n\n"
        f"Follow the steps at [link=https://kiln-ai.github.io/Kiln/kiln_core_docs/kiln_ai.html#run-a-kiln-task-from-python]"
        f"https://kiln-ai.github.io/Kiln/kiln_core_docs/kiln_ai.html#run-a-kiln-task-from-python[/link]\n"
        f"to load and run it from code."
    )

    return task_prompts
