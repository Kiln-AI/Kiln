"""Generate or check the Kiln skill's API reference.

    uv run python -m app.desktop.skill_api_reference generate
    uv run python -m app.desktop.skill_api_reference check

Both build the desktop app's OpenAPI document in process (no server, no
network), or read it from `--spec FILE`. Exit codes: 0 clean, 1 stale or
failed, 2 usage error.
"""

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from kiln_mcp_server.skill_checks.api_reference import (
    ApiReferenceError,
    diff_folder,
    render,
    write_folder,
)
from kiln_mcp_server.skill_checks.knowledge_schema import default_root
from kiln_mcp_server.skill_files import API_DOCS_FOLDER

from app.desktop.desktop_server import make_app

FIX_COMMAND = "uv run python -m app.desktop.skill_api_reference generate"
SKIPPED = "skipped: the generator needs Python 3.13\n"
GENERATOR_PYTHON = (3, 13)

Renderer = Callable[[dict], dict[str, bytes]]


def current_spec() -> dict:
    """The OpenAPI document of the desktop app, built in process."""
    os.environ["KILN_SKIP_REMOTE_MODEL_LIST"] = "true"
    return make_app().openapi()


def default_target() -> Path:
    return default_root() / API_DOCS_FOLDER


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.desktop.skill_api_reference",
        description="Generate or check the Kiln skill's API reference.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("generate", "rewrite the API reference folder"),
        ("check", "exit 1 when the API reference folder is stale"),
    ):
        command = commands.add_parser(name, help=text, description=text)
        command.add_argument(
            "--spec",
            type=Path,
            default=None,
            help="read the OpenAPI document from this JSON file in place of building the app",
        )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    target: Path | None = None,
    renderer: Renderer = render,
) -> int:
    args = _parser().parse_args(argv)
    if sys.version_info < GENERATOR_PYTHON:
        if args.command == "check":
            sys.stdout.write(SKIPPED)
            return 0
        sys.stderr.write("The generator needs Python 3.13.\n")
        return 2

    if args.spec is not None and not args.spec.is_file():
        sys.stderr.write(f"No such file: {args.spec}\n")
        return 2

    target = target if target is not None else default_target()
    if args.spec is None:
        spec = current_spec()
    else:
        try:
            spec = json.loads(args.spec.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            sys.stderr.write(f"{args.spec} is not a JSON file: {error}\n")
            return 2
        if not isinstance(spec, dict):
            sys.stderr.write(f"{args.spec} does not hold a JSON object\n")
            return 2
    try:
        files = renderer(spec)
    except ApiReferenceError as error:
        sys.stderr.write(f"Cannot generate the API reference: {error}\n")
        return 1

    if args.command == "generate":
        write_folder(files, target)
        sys.stdout.write(f"Wrote {len(files)} files to {target}\n")
        return 0

    differences = diff_folder(files, target)
    if not differences:
        sys.stdout.write("API reference up to date\n")
        return 0
    sys.stdout.write("The API reference is not current:\n")
    sys.stdout.writelines(f"  {line}\n" for line in differences)
    sys.stdout.write(f"Run `{FIX_COMMAND}` and commit the folder.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
