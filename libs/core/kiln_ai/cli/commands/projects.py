import typer
from rich.console import Console
from rich.table import Table

from kiln_ai.datamodel import Project
from kiln_ai.utils.config import Config

app = typer.Typer(help="Manage Kiln projects")
console = Console()


def print_projects_table(title: str = "Kiln Projects") -> int:
    """Print a table of available projects from the config.

    Returns:
        int: The number of successfully loaded projects.
    """
    project_paths = Config.shared().projects

    if not project_paths:
        console.print("[yellow]No projects configured.[/yellow]")
        console.print(
            "Use the Kiln web UI to create a project, or add one with 'kiln_ai projects add <path>'"
        )
        return 0

    table = Table(title=title)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Path", style="dim")

    loaded_count = 0
    for project_path in project_paths:
        try:
            project = Project.load_from_file(project_path)
            table.add_row(project.name, str(project_path))
            loaded_count += 1
        except Exception:
            table.add_row("[red]<failed to load>[/red]", str(project_path))

    console.print(table)
    return loaded_count


@app.command("list")
def list_projects() -> None:
    """List all configured projects."""
    loaded_count = print_projects_table()
    if loaded_count == 0:
        raise typer.Exit(0)
    console.print(f"\n[green]{loaded_count}[/green] project(s) loaded")
