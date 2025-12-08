import typer
from rich.console import Console
from rich.table import Table

from kiln_ai.datamodel import Project
from kiln_ai.utils.config import Config

app = typer.Typer(help="Manage Kiln projects")
console = Console()


@app.command("list")
def list_projects() -> None:
    """List all configured projects."""
    project_paths = Config.shared().projects

    if not project_paths:
        console.print("[yellow]No projects configured.[/yellow]")
        console.print(
            "Use the Kiln web UI to create a project, or add one with 'kiln_ai projects add <path>'"
        )
        raise typer.Exit(0)

    table = Table(title="Kiln Projects")
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
    console.print(f"\n[green]{loaded_count}[/green] project(s) loaded")
