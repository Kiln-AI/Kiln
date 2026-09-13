"""The object a world package builds and everything else hangs off.

`World` holds the schema, the registered tools, the middleware chain and the startup hooks,
and it is the factory for instances. Registration is open: a world can add a tool after an
instance exists, and the instance sees it, which is what makes a REPL session and a test
suite pleasant to work in.

Almost everything it can check, it checks at construction. The DDL has to run. Every tracked
table has to declare a primary key, and one that cannot be NULL, because the changes diff is
keyed on it. Every name in `untracked_tables` has to be a real table. Tool names may not
collide with each other or with the wire's own verbs. A world that imports is a world whose
shape is already known to be sound.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import inspect
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import control
from . import fixtures as fixtures_module
from .call import Handler, Middleware, StartupHook, build_chain, invoke
from .db import build_blank, quote, table_keys, world_tables
from .errors import WorldBug
from .fixtures import Fixture
from .instances import Instance, InstanceManager
from .tool import Tool

MINIMUM_PYTHON = (3, 12)

# The wire's own message types, plus the control tools, which are registered by the runtime.
RESERVED_TOOL_NAMES = frozenset(
    {
        "reset",
        "step",
        "state",
        "close",
        "controller_run_sql",
        "controller_changes",
        "controller_digest",
    }
)

_RESET_ARGUMENT_NAMES = frozenset({"fixture", "seed", "now"})


class World:
    def __init__(
        self,
        name: str,
        version: str,
        schema: str,
        *,
        fixtures_dir: Path | str | None = None,
        work_dir: Path | str | None = None,
        untracked_tables: Sequence[str] = (),
    ) -> None:
        if sys.version_info < MINIMUM_PYTHON:
            raise WorldBug(
                "the worlds runtime needs Python "
                f"{MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} or newer for sqlite3's "
                f"autocommit mode and setconfig; this is {sys.version.split()[0]}"
            )
        if not version:
            raise WorldBug(f"world '{name}' needs a non-empty version")
        self.name = name
        self.version = version
        self.schema = schema
        self.schema_hash = hashlib.sha256(
            re.sub(r"\s+", " ", schema).strip().encode("utf-8")
        ).hexdigest()
        self.untracked_tables = tuple(untracked_tables)
        self.work_dir = Path(work_dir) if work_dir is not None else None
        self.fixtures_dir = (
            Path(fixtures_dir) if fixtures_dir is not None else _derive_fixtures_dir()
        )

        reference = build_blank(":memory:", schema)
        try:
            tables = world_tables(reference)
            unknown = sorted(set(self.untracked_tables) - set(tables))
            if unknown:
                raise WorldBug(
                    f"untracked_tables names {unknown}, which the schema does not define; "
                    "a misspelled name would leave the table tracked with no warning"
                )
            self.tracked_tables = tuple(
                sorted(t for t in tables if t not in self.untracked_tables)
            )
            for table in self.tracked_tables:
                keys, _ = table_keys(reference, table)
                if not keys:
                    raise WorldBug(
                        f"table '{table}' has no explicit primary key; add one or list "
                        "it in untracked_tables"
                    )
                nullable = _nullable_key_columns(reference, table, keys)
                if nullable:
                    raise WorldBug(
                        f"table '{table}' allows NULL in primary key column(s) {nullable}; "
                        "the changes diff joins on the key with IS, so two NULL-keyed rows "
                        "would match each other and report edits that never happened. "
                        "Declare the column NOT NULL, make the table STRICT, or list the "
                        "table in untracked_tables"
                    )
        finally:
            reference.close()

        self._tools: dict[str, Tool] = {}
        self._middlewares: list[Middleware] = []
        self._startup_hooks: list[StartupHook] = []
        self._startup_hook_kwargs: list[frozenset[str] | None] = []
        self._manager: InstanceManager | None = None
        self.chain: Handler = build_chain(self._middlewares, invoke)
        for tool in control.control_tools():
            self._tools[tool.name] = tool

    # ---- registration ----

    @property
    def tools(self) -> Mapping[str, Tool]:
        return self._tools

    @property
    def middlewares(self) -> Sequence[Middleware]:
        return tuple(self._middlewares)

    @property
    def startup_hooks(self) -> Sequence[StartupHook]:
        return tuple(self._startup_hooks)

    @property
    def startup_hook_kwargs(self) -> Sequence[frozenset[str] | None]:
        """Per hook, the reset arguments it accepts; `None` where a hook takes `**kwargs`."""
        return tuple(self._startup_hook_kwargs)

    @property
    def accepted_startup_kwargs(self) -> frozenset[str] | None:
        """Every reset argument some hook accepts, or `None` when a hook takes them all."""
        accepted: set[str] = set()
        for names in self._startup_hook_kwargs:
            if names is None:
                return None
            accepted.update(names)
        return frozenset(accepted)

    def tool(
        self,
        obj: Callable[..., Any] | Tool | None = None,
        /,
        *,
        name: str | None = None,
        description: str | None = None,
        transaction: bool = True,
    ) -> Any:
        def register(target: Callable[..., Any] | Tool) -> Any:
            if isinstance(target, Tool):
                if (
                    name is not None
                    or description is not None
                    or transaction is not True
                ):
                    raise WorldBug(
                        f"tool '{target.name}' was built already; its options cannot be "
                        "changed at registration"
                    )
                built = target
            else:
                built = Tool.from_function(
                    target, name=name, description=description, transaction=transaction
                )
            if built.name in RESERVED_TOOL_NAMES:
                raise WorldBug(
                    f"'{built.name}' is reserved by the runtime; choose another name"
                )
            if built.name in self._tools:
                raise WorldBug(f"a tool named '{built.name}' is already registered")
            self._tools[built.name] = built
            return target

        return register if obj is None else register(obj)

    def middleware(self, obj: Middleware | None = None, /) -> Any:
        def register(target: Middleware) -> Middleware:
            _check_middleware(target)
            self._middlewares.append(target)
            self.chain = build_chain(self._middlewares, invoke)
            return target

        return register if obj is None else register(obj)

    def instance_startup(self, obj: StartupHook | None = None, /) -> Any:
        def register(target: StartupHook) -> StartupHook:
            self._startup_hooks.append(target)
            self._startup_hook_kwargs.append(_startup_hook_kwargs(target))
            return target

        return register if obj is None else register(obj)

    def set_version(self, version: str) -> None:
        """Replace the reported version. Nothing caches it, so `/metadata` and the next
        freeze both read the new string."""
        if not version:
            raise WorldBug("a world version cannot be empty")
        self.version = version

    # ---- instances and fixtures ----

    def instance(
        self,
        fixture: str | None,
        *,
        seed: int | bytes | None = None,
        now: str | datetime | None = None,
        **startup_kwargs: Any,
    ) -> Instance:
        if self._manager is None:
            self._manager = InstanceManager(self)
        return self._manager.create(
            fixture, seed=seed, now=now, startup_kwargs=startup_kwargs
        )

    def fixtures(self) -> list[Fixture]:
        return list(fixtures_module.load_all(self.fixtures_dir).values())

    def fixture(self, fixture_id: str) -> Fixture:
        fixtures_module.check_id(fixture_id)
        directory = self.fixtures_dir / fixture_id
        if not directory.is_dir():
            raise WorldBug(
                f"world '{self.name}' has no fixture '{fixture_id}' in {self.fixtures_dir}"
            )
        return fixtures_module.load(directory)


def sql_files(package: str, directory: str) -> str:
    """Every `.sql` file under `package/directory`, name-sorted and concatenated, so schema
    files can be numbered and read in order."""
    root = importlib.resources.files(package) / directory
    parts = [
        entry.read_text(encoding="utf-8")
        for entry in sorted(root.iterdir(), key=lambda entry: entry.name)
        if entry.name.endswith(".sql")
    ]
    return "\n".join(parts)


def _nullable_key_columns(
    conn: sqlite3.Connection, table: str, keys: Sequence[str]
) -> list[str]:
    """Primary key columns of `table` that can actually hold NULL.

    STRICT and WITHOUT ROWID tables report their key columns as NOT NULL, so only a plain
    rowid table with an undeclared key column is at risk. The one exception is an
    `INTEGER PRIMARY KEY`: it is an alias for the rowid, and SQLite fills it in rather than
    storing the NULL it was handed.
    """
    info = {
        row[1]: row
        for row in conn.execute(f"PRAGMA table_info({quote(table)})").fetchall()
    }
    without_rowid = any(
        row[1] == table and row[0] == "main" and row[4]
        for row in conn.execute("PRAGMA table_list").fetchall()
    )
    if len(keys) == 1 and not without_rowid:
        # A rowid alias has no primary-key index. `INTEGER PRIMARY KEY DESC` builds one,
        # is not an alias, and really can store NULL, so it is not exempt.
        aliases_rowid = not any(
            row[3] == "pk"
            for row in conn.execute(f"PRAGMA index_list({quote(table)})").fetchall()
        )
        if aliases_rowid and str(info[keys[0]][2] or "").strip().upper() == "INTEGER":
            return []
    return [key for key in keys if not info[key][3]]


def _check_middleware(target: Middleware) -> None:
    signature = inspect.signature(target)
    positional = [
        p
        for p in signature.parameters.values()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    if any(
        p.kind is inspect.Parameter.VAR_POSITIONAL
        for p in signature.parameters.values()
    ):
        return
    if len(positional) != 3:
        raise WorldBug(
            f"middleware '{getattr(target, '__name__', target)}' must take "
            "(ctx, call, next_handler)"
        )


def _startup_hook_kwargs(target: StartupHook) -> frozenset[str] | None:
    signature = inspect.signature(target)
    parameters = list(signature.parameters.values())
    where = f"startup hook '{getattr(target, '__name__', target)}'"
    positional = [
        p
        for p in parameters
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    if len(positional) != 1:
        raise WorldBug(f"{where} must take the context as its only positional argument")
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in parameters):
        raise WorldBug(f"{where} must not take *args")
    accepted: set[str] = set()
    for parameter in parameters[1:]:
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return None
        if parameter.name in _RESET_ARGUMENT_NAMES:
            raise WorldBug(
                f"{where} declares '{parameter.name}', which reset already means; "
                "rename it"
            )
        accepted.add(parameter.name)
    return frozenset(accepted)


def _derive_fixtures_dir() -> Path:
    """`fixtures/` beside the caller's `pyproject.toml`, or beside the caller itself.

    A world is authored as a package with fixtures at its root; deriving the path means a
    world's `World(...)` line carries no absolute paths and moves with the checkout.
    """
    runtime = Path(__file__).resolve().parent
    caller: Path | None = None
    for frame in inspect.stack()[1:]:
        candidate = Path(frame.filename).resolve()
        if candidate.parent != runtime:
            caller = candidate
            break
    if caller is None:
        return Path.cwd() / "fixtures"
    for parent in [caller.parent, *caller.parent.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent / "fixtures"
    return caller.parent / "fixtures"
