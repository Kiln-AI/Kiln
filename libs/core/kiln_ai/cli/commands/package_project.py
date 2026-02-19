import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.table import Table

from kiln_ai.adapters.prompt_builders import BasePromptBuilder, prompt_builder_from_id
from kiln_ai.cli.commands.projects import print_projects_table
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.external_tool_server import ExternalToolServer
from kiln_ai.datamodel.prompt import Prompt
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.tool_id import (
    KILN_TASK_TOOL_ID_PREFIX,
    MCP_LOCAL_TOOL_ID_PREFIX,
    MCP_REMOTE_TOOL_ID_PREFIX,
    RAG_TOOL_ID_PREFIX,
    KilnBuiltInToolId,
    kiln_task_server_id_from_tool_id,
    mcp_server_and_tool_name_from_id,
)

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


def get_tools_from_run_config(run_config: TaskRunConfig) -> list[str]:
    """Get the list of tool IDs from a run config."""
    if not isinstance(run_config.run_config_properties, KilnAgentRunConfigProperties):
        return []
    if (
        run_config.run_config_properties.tools_config
        and run_config.run_config_properties.tools_config.tools
    ):
        return run_config.run_config_properties.tools_config.tools
    return []


def collect_subtask_ids_from_tools(
    task_ids: list[str], project: Project
) -> tuple[set[str], list[str]]:
    """Collect additional task IDs needed as sub-tasks from kiln_task tools.

    This runs early, before full task validation, to discover sub-tasks that
    need to be included in the export.

    Args:
        task_ids: Initial list of task IDs to export
        project: The project containing the tasks

    Returns:
        Tuple of (additional_task_ids, subtask_names) where:
        - additional_task_ids: Set of task IDs to add to export
        - subtask_names: List of task names for display
    """
    additional_task_ids: set[str] = set()
    subtask_names: list[str] = []
    available_tasks = project.tasks()
    task_id_to_task = {task.id: task for task in available_tasks if task.id}
    external_servers = project.external_tool_servers()
    server_id_to_server = {
        server.id: server for server in external_servers if server.id
    }

    for task_id in task_ids:
        if task_id not in task_id_to_task:
            continue

        task = task_id_to_task[task_id]
        if not task.default_run_config_id:
            continue

        run_configs = task.run_configs()
        run_config = next(
            (rc for rc in run_configs if rc.id == task.default_run_config_id), None
        )
        if not run_config:
            continue

        tools = get_tools_from_run_config(run_config)
        for tool_id in tools:
            if tool_id.startswith(KILN_TASK_TOOL_ID_PREFIX):
                server_id = kiln_task_server_id_from_tool_id(tool_id)
                server = server_id_to_server.get(server_id)
                if server and server.properties:
                    subtask_id = server.properties.get("task_id")
                    if (
                        subtask_id
                        and subtask_id not in task_ids
                        and subtask_id not in additional_task_ids
                    ):
                        additional_task_ids.add(subtask_id)
                        subtask = task_id_to_task.get(subtask_id)
                        if subtask:
                            subtask_names.append(subtask.name)

    return additional_task_ids, subtask_names


def classify_tool_id(
    tool_id: str,
) -> Literal["builtin", "kiln_task", "mcp_remote", "mcp_local", "rag", "unknown"]:
    """Classify a tool ID into its type category.

    Returns one of: 'builtin', 'kiln_task', 'mcp_remote', 'mcp_local', 'rag', 'unknown'
    """
    if tool_id in [member.value for member in KilnBuiltInToolId]:
        return "builtin"
    elif tool_id.startswith(KILN_TASK_TOOL_ID_PREFIX):
        return "kiln_task"
    elif tool_id.startswith(MCP_REMOTE_TOOL_ID_PREFIX):
        return "mcp_remote"
    elif tool_id.startswith(MCP_LOCAL_TOOL_ID_PREFIX):
        return "mcp_local"
    elif tool_id.startswith(RAG_TOOL_ID_PREFIX):
        return "rag"
    else:
        return "unknown"


def validate_tools(tasks: list[Task], run_configs: dict[str, TaskRunConfig]) -> None:
    """Validate all tools in the run configs and handle each type appropriately.

    Args:
        tasks: List of tasks to validate
        run_configs: Dictionary mapping task IDs to their run configs

    Raises:
        typer.Exit: If validation fails or user declines to continue
    """
    has_mcp_local = False
    mcp_local_task_names: list[str] = []
    has_mcp_remote = False
    mcp_remote_task_names: list[str] = []

    for task in tasks:
        run_config = run_configs.get(task.id)  # type: ignore
        if not run_config:
            continue

        tools = get_tools_from_run_config(run_config)
        for tool_id in tools:
            tool_type = classify_tool_id(tool_id)

            if tool_type == "builtin":
                # Built-in tools are fine, no action needed
                pass
            elif tool_type == "kiln_task":
                # Kiln task tools are handled by collect_subtask_ids_from_tools
                pass
            elif tool_type == "mcp_remote":
                # Remote MCP tools are fine, no action needed
                if task.name not in mcp_remote_task_names:
                    has_mcp_remote = True
                    mcp_remote_task_names.append(task.name)
                pass
            elif tool_type == "mcp_local":
                # Track for later prompt
                if task.name not in mcp_local_task_names:
                    has_mcp_local = True
                    mcp_local_task_names.append(task.name)
                pass
            elif tool_type == "rag":
                console.print(f"[red]Error:[/red] Task '{task.name}' uses a RAG tool.")
                console.print(
                    "\nThe project package tool does not currently support running tasks with RAG. "
                    "We have dedicated instructions for deploying Kiln RAG tasks here:\n"
                    "[link=https://docs.kiln.tech/docs/documents-and-search-rag#deploying-your-rag]"
                    "https://docs.kiln.tech/docs/documents-and-search-rag#deploying-your-rag[/link]"
                )
                raise typer.Exit(1)
            else:
                console.print(
                    f'[red]Error:[/red] This task uses an unrecognized tool type: "{tool_id}". '
                    "Please contact Kiln team for assistance."
                )
                raise typer.Exit(1)

    # Prompt for MCP local tools after checking all tasks
    if has_mcp_local:
        console.print(
            f"\n[yellow]Warning:[/yellow] The following tasks require local MCP tools: "
            f"{', '.join(mcp_local_task_names)}"
        )
        console.print(
            "\nThis task requires a MCP tool. You'll need to manually install the needed "
            "MCP server on any machine you run this task on."
        )
        if not typer.confirm("Continue?"):
            raise typer.Exit(0)

    if has_mcp_remote:
        console.print(
            f"\n[yellow]Warning:[/yellow] The following tasks require remote MCP tools: "
            f"{', '.join(mcp_remote_task_names)}"
        )
        console.print(
            "\nThese remote MCP tools may require configuring secrets like API keys or other credentials. This must be done on any machine you run this task on."
        )
        if not typer.confirm("Continue?"):
            raise typer.Exit(0)


def collect_required_tool_servers(
    tasks: list[Task], run_configs: dict[str, TaskRunConfig]
) -> set[str]:
    """Collect the IDs of external tool servers needed by the tasks.

    Args:
        tasks: List of tasks to check
        run_configs: Dictionary mapping task IDs to their run configs

    Returns:
        Set of server IDs that need to be exported
    """
    server_ids: set[str] = set()

    for task in tasks:
        run_config = run_configs.get(task.id)  # type: ignore
        if not run_config:
            continue

        tools = get_tools_from_run_config(run_config)
        for tool_id in tools:
            tool_type = classify_tool_id(tool_id)

            if tool_type == "kiln_task":
                server_id = kiln_task_server_id_from_tool_id(tool_id)
                server_ids.add(server_id)
            elif tool_type in ("mcp_remote", "mcp_local"):
                server_id, _ = mcp_server_and_tool_name_from_id(tool_id)
                server_ids.add(server_id)

    return server_ids


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
        if not isinstance(
            run_config.run_config_properties, KilnAgentRunConfigProperties
        ):
            console.print(
                f"[red]Error:[/red] Task '{task.name}' uses a non-kiln_agent run config. Project export requires kiln_agent run configs."
            )
            raise typer.Exit(1)
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
        if not isinstance(
            run_config.run_config_properties, KilnAgentRunConfigProperties
        ):
            console.print(
                f"[red]Error:[/red] Task '{task.name}' uses a non-kiln_agent run config. Project export requires kiln_agent run configs."
            )
            raise typer.Exit(1)
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

    if isinstance(
        exported_run_config.run_config_properties, KilnAgentRunConfigProperties
    ):
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


def export_tool_servers(
    server_ids: set[str],
    project: Project,
    exported_project: Project,
) -> None:
    """Export external tool servers needed by the tasks.

    Args:
        server_ids: Set of server IDs to export
        project: The original project
        exported_project: The exported project to copy servers into
    """
    if not server_ids:
        return

    if exported_project.path is None:
        raise ValueError("Exported project path is not set")

    for server in project.external_tool_servers():
        if server.id not in server_ids:
            continue
        if server.path is None:
            raise ValueError(f"Server '{server.name}' path is not set")

        folder_name = server.path.parent.name
        server_dir = (
            exported_project.path.parent / "external_tool_servers" / folder_name
        )
        server_dir.mkdir(parents=True, exist_ok=True)

        exported_server_path = server_dir / "external_tool_server.kiln"
        shutil.copy(server.path, exported_server_path)

        exported_server = ExternalToolServer.load_from_file(exported_server_path)
        exported_server.parent = exported_project


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

    # 3. Collect additional task IDs from kiln_task tools (sub-tasks)
    additional_task_ids, subtask_names = collect_subtask_ids_from_tools(
        task_ids, project
    )
    if additional_task_ids:
        console.print(
            f"[cyan]Adding {len(additional_task_ids)} task(s) to export. "
            f"These are required as sub-tasks: {', '.join(subtask_names)}[/cyan]"
        )
        task_ids = list(set(task_ids) | additional_task_ids)

    validated_tasks = validate_tasks(task_ids, project)
    console.print(
        f"[green]✓[/green] Validated {len(validated_tasks)} task(s): {', '.join(t.name for t in validated_tasks)}"
    )

    # 4. Validate run configs
    run_configs: dict[str, TaskRunConfig] = {}
    for task in validated_tasks:
        run_config = get_default_run_config(task)
        run_configs[task.id] = run_config  # type: ignore

    console.print("[green]✓[/green] Validated default run configs")

    # 5. Validate all tools in run configs
    validate_tools(validated_tasks, run_configs)
    console.print("[green]✓[/green] Validated tools")

    # 6. Collect required tool servers
    required_server_ids = collect_required_tool_servers(validated_tasks, run_configs)

    # 7. Build and validate prompts
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

        # 5. Export required tool servers
        export_tool_servers(required_server_ids, project, exported_project)
        if required_server_ids:
            console.print(
                f"[green]✓[/green] Exported {len(required_server_ids)} tool server(s)"
            )

        # 6. Create zip file
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
