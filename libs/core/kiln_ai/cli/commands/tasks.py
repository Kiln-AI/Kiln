from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kiln_ai.datamodel import Project

app = typer.Typer(help="Manage Kiln tasks")
console = Console()


@app.command("list")
def list_tasks(
    project_path: str = typer.Argument(help="Path to the project file"),
) -> None:
    """List all tasks in a project."""
    path = Path(project_path)

    if not path.exists():
        console.print(f"[red]Error: Project file not found: {project_path}[/red]")
        raise typer.Exit(1)

    try:
        project = Project.load_from_file(path)
    except Exception as e:
        console.print(f"[red]Error loading project: {e}[/red]")
        raise typer.Exit(1)

    tasks = project.tasks(readonly=True)

    if not tasks:
        console.print("[yellow]No tasks found in this project.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f"Tasks in {project.name}")
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
