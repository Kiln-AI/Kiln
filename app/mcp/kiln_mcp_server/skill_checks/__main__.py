"""The command line of the skill checks.

    uv run python -m kiln_mcp_server.skill_checks check [--root DIR]
    uv run python -m kiln_mcp_server.skill_checks build [--root DIR]

`check` runs the tree check, the knowledge check and the docs index check, and
prints one line per problem (`rule  path  message`). `build` rewrites the
generated blocks of the knowledge index files and `docs_index.md`, prints one
`rewrote <file>` line per changed file, then checks. Exit codes: 0 clean,
1 problems, 2 usage error or missing folder.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from kiln_mcp_server.skill_checks.docs_index import (
    docs_index_problems,
    write_docs_index,
)
from kiln_mcp_server.skill_checks.knowledge_check import check
from kiln_mcp_server.skill_checks.knowledge_index import write_blocks
from kiln_mcp_server.skill_checks.knowledge_load import load
from kiln_mcp_server.skill_checks.knowledge_schema import Problem, default_root
from kiln_mcp_server.skill_checks.tree_check import check_tree, tree_paths


def run_check(root: Path) -> list[Problem]:
    """Every problem of the skill folder `root`: the tree first, in file
    order, then the knowledge trees, then the docs index."""
    return [
        *check_tree(root),
        *check(load(root), tree=tree_paths(root)),
        *docs_index_problems(root),
    ]


def run_build(root: Path) -> list[Path]:
    """Rewrite every generated index of `root`. Returns the files that changed."""
    changed = write_blocks(load(root))
    docs_index = write_docs_index(root)
    return [*changed, docs_index] if docs_index is not None else changed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m kiln_mcp_server.skill_checks",
        description="Check the Kiln skill tree, or rebuild its generated indexes.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("check", "report each broken rule; exit 1 when there is one"),
        ("build", "rewrite the generated indexes, then check"),
    ):
        command = commands.add_parser(name, help=text, description=text)
        command.add_argument(
            "--root",
            type=Path,
            default=None,
            help="the skill folder (default: the package's own)",
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root if args.root is not None else default_root()
    if not root.is_dir():
        sys.stderr.write(f"No skill folder at {root}\n")
        return 2
    if args.command == "build":
        sys.stdout.writelines(f"rewrote {path}\n" for path in run_build(root))
    problems = run_check(root)
    sys.stdout.writelines(
        f"{problem.rule}  {problem.path}  {problem.message}\n" for problem in problems
    )
    if problems:
        sys.stdout.write(f"{len(problems)} problems\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
