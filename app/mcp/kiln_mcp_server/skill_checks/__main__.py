"""The command line of the skill checks.

    uv run python -m kiln_mcp_server.skill_checks check [--root DIR]

`check` prints one line per problem (`rule  path  message`). Exit codes: 0
clean, 1 problems, 2 usage error or missing folder.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from kiln_mcp_server.skill_checks.tree_check import check_tree, default_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m kiln_mcp_server.skill_checks",
        description="Check the Kiln skill tree.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    text = "report each broken rule; exit 1 when there is one"
    command = commands.add_parser("check", help=text, description=text)
    command.add_argument(
        "--root",
        type=Path,
        default=None,
        help="the skill folder to check (default: the package's own)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root if args.root is not None else default_root()
    if not root.is_dir():
        sys.stderr.write(f"No skill folder at {root}\n")
        return 2
    problems = check_tree(root)
    sys.stdout.writelines(
        f"{problem.rule}  {problem.path}  {problem.message}\n" for problem in problems
    )
    if problems:
        sys.stdout.write(f"{len(problems)} problems\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
