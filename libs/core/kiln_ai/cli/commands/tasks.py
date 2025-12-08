from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kiln_ai.datamodel import Project
from kiln_ai.utils.config import Config

app = typer.Typer(help="Manage Kiln tasks")
console = Console()


def load_project_by_id(project_id: str) -> Project | None:
    """Load a project by its ID from the config.

    Returns:
        Project if found and loaded successfully, None otherwise.
    """
    project_paths = Config.shared().projects
    for project_path in project_paths:
        try:
            project = Project.load_from_file(project_path)
            if project.id == project_id:
                return project
        except Exception:
            continue
    return None


def load_project(project_ref: str) -> Project:
    """Load a project by path or ID.

    Args:
        project_ref: Either a file path to a project file, or a project ID.

    Returns:
        The loaded Project.

    Raises:
        typer.Exit: If project cannot be found or loaded.
    """
    path = Path(project_ref)
    if path.exists():
        try:
            return Project.load_from_file(path)
        except Exception as e:
            console.print(f"[red]Error loading project: {e}[/red]")
            raise typer.Exit(1)

    project = load_project_by_id(project_ref)
    if project is not None:
        return project

    console.print(f"[red]Error: Project not found: {project_ref}[/red]")
    console.print("Provide a valid project file path or project ID.")
    console.print("Use 'kiln project list' to see available projects.")
    raise typer.Exit(1)


@app.command("list")
def list_tasks(
    project: str = typer.Argument(help="Project file path or project ID"),
) -> None:
    """List all tasks in a project."""
    loaded_project = load_project(project)

    tasks = loaded_project.tasks(readonly=True)

    if not tasks:
        console.print("[yellow]No tasks found in this project.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"Tasks in {loaded_project.name}")
    table.add_column("ID", no_wrap=True)
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Path", style="dim")

    for task in tasks:
        table.add_row(
            task.id,
            task.name,
            task.description or "",
            str(task.path) if task.path else "",
        )

    console.print(table)
    console.print(f"\n[green]{len(tasks)}[/green] task(s) found")
