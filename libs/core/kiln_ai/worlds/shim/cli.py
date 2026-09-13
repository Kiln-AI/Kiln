"""Three verbs: serve a world, freeze a fixture from it, fork an existing fixture.

Deliberately small. There is no package discovery and no scaffolding: a world is named as
`module:attribute`, the way uvicorn names an app, so the command line says exactly what it
loaded.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import Any, Sequence

from . import fixtures as fixtures_module
from .errors import SeahavenError
from .fixtures import SIDECAR_NAME, Fixture
from .instances import set_concurrency_gate
from .version import write_version
from .world import World


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as e:
        return int(e.code or 0)
    try:
        return _run(args)
    except SeahavenError as e:
        print(str(e), file=sys.stderr)
        return 1
    except (ImportError, AttributeError, OSError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m kiln_ai.worlds.shim",
        description="Serve a world, or build a fixture for it.",
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    serve = verbs.add_parser("serve", help="serve a world over the OpenEnv wire")
    serve.add_argument("world", help="the world, as module:attribute")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--max-concurrent-envs", type=int, default=500)
    serve.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="how many tool calls may run at once across sessions (0 disables the gate)",
    )
    serve.add_argument("--session-timeout", type=float, default=3600.0)
    serve.add_argument("--include-control-tools", action="store_true")

    freeze = verbs.add_parser(
        "freeze", help="freeze a new fixture from a blank instance"
    )
    freeze.add_argument("world", help="the world, as module:attribute")
    freeze.add_argument("id", help="the new fixture's id")
    freeze.add_argument(
        "--run", required=True, help="the generator, as module:function"
    )
    freeze.add_argument("--description", required=True)
    freeze.add_argument("--now", default=None, help="the fixture's timestamp")

    fork = verbs.add_parser("fork", help="freeze a new fixture from an existing one")
    fork.add_argument("world", help="the world, as module:attribute")
    fork.add_argument("parent", help="the fixture to fork")
    fork.add_argument("id", help="the new fixture's id")
    fork.add_argument("--run", required=True, help="the mutation, as module:function")
    fork.add_argument("--description", required=True)
    return parser


def _run(args: argparse.Namespace) -> int:
    world = _load(args.world, World)
    if args.verb == "serve":
        return _serve(world, args)
    generator = _load(args.run)
    if args.verb == "freeze":
        instance = world.instance(None, now=args.now)
        try:
            generator(instance)
            fixture = instance.freeze(args.id, args.description)
        finally:
            instance.destroy()
    else:
        fixture = fixtures_module.fork(
            world, args.parent, args.id, generator, description=args.description
        )
    _report(world, fixture)
    return 0


def _serve(world: World, args: argparse.Namespace) -> int:
    import uvicorn

    from .openenv import app

    if args.concurrency is not None:
        set_concurrency_gate(args.concurrency)
    uvicorn.run(
        app(
            world,
            include_control_tools=args.include_control_tools,
            max_concurrent_envs=args.max_concurrent_envs,
            session_timeout=args.session_timeout,
        ),
        host=args.host,
        port=args.port,
    )
    return 0


def _report(world: World, fixture: Fixture) -> None:
    print((fixture.dir / SIDECAR_NAME).read_text(encoding="utf-8"), end="")
    # The new fixture changes the package's fixtures digest, so the pinned version moves.
    print(write_version(world.fixtures_dir.parent))


def _load(spec: str, expected: type | None = None) -> Any:
    if ":" not in spec:
        raise ValueError(f"{spec!r} must be written module:attribute")
    module_name, _, attribute = spec.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise ImportError(f"could not import {module_name!r}: {e}") from e
    try:
        value = getattr(module, attribute)
    except AttributeError as e:
        raise AttributeError(f"{module_name!r} has no attribute {attribute!r}") from e
    if expected is not None and not isinstance(value, expected):
        raise ValueError(f"{spec!r} is not a {expected.__name__}")
    return value
