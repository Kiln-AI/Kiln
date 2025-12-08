import typer

from kiln_ai.cli.commands import package_project, projects, tasks

app = typer.Typer(
    help="Kiln AI CLI - Build AI systems with evals, data gen, fine-tuning, and more.",
    no_args_is_help=True,
)

app.add_typer(projects.app, name="projects")
app.add_typer(tasks.app, name="tasks")
app.command(name="package_project")(package_project.package_project)
