"""The per-instance SQLite runtime.

Two connection shapes. `open_instance` is the writable one a tool runs against: autocommit
at the driver level so nothing opens a transaction implicitly, which is what lets
`transaction()` own nesting explicitly and lets `VACUUM INTO` and `ATTACH` run whenever the
depth is zero. `open_inspection` is read-only, with a SQLite authorizer that denies every
write, every schema change and every pragma outside a small introspection allowlist; the
changes diff, the digest and the `controller_run_sql` control tool all run there.

Parameters are positional `?` only. Seahaven made the same call and the reason is the same:
one parameter style means a tool cannot half-build a query from a dict and leave an
injection seam.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import (
    AbstractSet,
    Any,
    Iterable,
    Iterator,
    Mapping,
    Optional,
    Sequence,
    Union,
)

from .clock import Clock, register_clock_functions
from .errors import DbError, WorldBug

SqlValue = Union[None, int, float, str, bytes]

_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=0",
)

# Introspection only: enough for `pragma table_info` and friends, nothing that changes how
# the file behaves.
_ALLOWED_PRAGMAS = frozenset(
    {
        "table_info",
        "table_xinfo",
        "foreign_key_list",
        "index_list",
        "index_info",
        "index_xinfo",
        "schema_version",
        "user_version",
        "database_list",
        "table_list",
    }
)


def _denied_actions() -> AbstractSet[int]:
    names = {
        "SQLITE_INSERT",
        "SQLITE_UPDATE",
        "SQLITE_DELETE",
        "SQLITE_ALTER_TABLE",
        "SQLITE_REINDEX",
        "SQLITE_ATTACH",
        "SQLITE_DETACH",
        "SQLITE_TRANSACTION",
        "SQLITE_SAVEPOINT",
    }
    names.update(
        n
        for n in dir(sqlite3)
        if n.startswith("SQLITE_CREATE_") or n.startswith("SQLITE_DROP_")
    )
    return {getattr(sqlite3, n) for n in names if isinstance(getattr(sqlite3, n), int)}


_DENIED = _denied_actions()


def _deny_writes(
    action: int,
    arg1: Optional[str],
    arg2: Optional[str],
    db_name: Optional[str],
    trigger: Optional[str],
) -> int:
    if action in _DENIED:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and (arg1 or "").lower() not in _ALLOWED_PRAGMAS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


@contextmanager
def _wrapped() -> Iterator[None]:
    try:
        yield
    except sqlite3.Error as e:
        raise DbError(str(e), sqlite_code=getattr(e, "sqlite_errorcode", None)) from e


def _check_params(params: Sequence[Any]) -> None:
    for p in params:
        if isinstance(p, Mapping):
            raise WorldBug(
                "SQL parameters are positional '?' values; a mapping was passed, which "
                "means the query is using named parameters"
            )


@dataclass(frozen=True)
class Exec:
    """What a write statement did."""

    rowcount: int
    last_rowid: int | None


class Db:
    def __init__(self, conn: sqlite3.Connection, helper: sqlite3.Connection) -> None:
        self._conn = conn
        self._helper = helper
        self._depth = 0
        self._closed = False

    # ---- reads and writes ----

    def one(self, sql: str, *params: SqlValue) -> dict[str, Any] | None:
        _check_params(params)
        with _wrapped():
            cursor = self._conn.execute(sql, params)
            row = cursor.fetchone()
            return None if row is None else _as_dict(cursor, row)

    def rows(self, sql: str, *params: SqlValue) -> list[dict[str, Any]]:
        _check_params(params)
        with _wrapped():
            cursor = self._conn.execute(sql, params)
            return [_as_dict(cursor, row) for row in cursor.fetchall()]

    def execute(self, sql: str, *params: SqlValue) -> Exec:
        _check_params(params)
        with _wrapped():
            cursor = self._conn.execute(sql, params)
            return Exec(cursor.rowcount, cursor.lastrowid)

    def executemany(self, sql: str, rows: Iterable[Sequence[SqlValue]]) -> int:
        materialised = [tuple(row) for row in rows]
        for row in materialised:
            _check_params(row)
        with _wrapped():
            return self._conn.executemany(sql, materialised).rowcount

    # ---- transactions ----

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Nesting-aware: a real transaction at the top, savepoints below it, so a tool that
        calls a helper that also wants atomicity gets one commit, not two."""
        depth = self._depth
        savepoint = f"sp{depth}"
        with _wrapped():
            self._conn.execute(
                "BEGIN IMMEDIATE" if depth == 0 else f"SAVEPOINT {savepoint}"
            )
        self._depth = depth + 1
        try:
            yield
        except BaseException:
            self._depth = depth
            with _wrapped():
                if depth == 0:
                    self._conn.execute("ROLLBACK")
                else:
                    self._conn.execute(f"ROLLBACK TO {savepoint}")
                    self._conn.execute(f"RELEASE {savepoint}")
            raise
        self._depth = depth
        with _wrapped():
            self._conn.execute("COMMIT" if depth == 0 else f"RELEASE {savepoint}")

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    @property
    def in_transaction(self) -> bool:
        return self._conn.in_transaction

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._conn.close()
        finally:
            self._helper.close()


def _as_dict(cursor: sqlite3.Cursor, row: Sequence[Any]) -> dict[str, Any]:
    return {column[0]: value for column, value in zip(cursor.description, row)}


def quote(identifier: str) -> str:
    """Quote a SQLite identifier. Table and column names reach the diff from the world's own
    schema, never from an agent, but they still go through here so a column named `order`
    does not become a syntax error."""
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def open_instance(path: Path, clock: Clock) -> Db:
    # `autocommit=` and `setconfig` are 3.12+. `World.__init__` enforces that floor at
    # runtime; the module still parses on 3.10, which is what kiln-ai declares and what the
    # type checker assumes, hence the suppressions.
    conn = sqlite3.connect(  # ty: ignore[no-matching-overload]
        str(path),
        autocommit=True,
        check_same_thread=False,
        isolation_level=None,
        uri=False,
    )
    conn.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)  # ty: ignore[unresolved-attribute]
    try:
        conn.enable_load_extension(False)
    except AttributeError:
        pass
    for pragma in _PRAGMAS:
        conn.execute(pragma)
    helper = register_clock_functions(conn, clock)
    return Db(conn, helper)


def open_inspection(path: Path, clock: Clock, *, attach: Mapping[str, Path] = {}) -> Db:
    """A read-only view of an instance, optionally with other databases attached.

    The authorizer goes on after the attaches, because the changes diff needs the baseline
    attached and nothing after that needs `ATTACH` at all.
    """
    conn = sqlite3.connect(  # ty: ignore[no-matching-overload]
        f"file:{path}?mode=ro", uri=True, autocommit=True, check_same_thread=False
    )
    for name, other in attach.items():
        conn.execute(f"ATTACH ? AS {quote(name)}", (f"file:{other}?mode=ro",))
    helper = register_clock_functions(conn, clock)
    conn.set_authorizer(_deny_writes)
    return Db(conn, helper)


def build_blank(path: Path | str, ddl: str) -> sqlite3.Connection:
    """Create a database from the world's DDL. Refuses to touch a file that exists, so a
    blank-instance path can never clobber a fixture."""
    if str(path) != ":memory:" and Path(path).exists():
        raise WorldBug(f"refusing to build a blank database over {path}, which exists")
    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        conn.executescript(ddl)
    except sqlite3.Error as e:
        conn.close()
        raise WorldBug(f"the world's schema failed to run: {e}") from e
    conn.commit()
    return conn


def world_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]


def table_keys(conn: sqlite3.Connection, table: str) -> tuple[list[str], list[str]]:
    """`(primary key columns in key order, every other column in declaration order)`."""
    info = conn.execute(f"PRAGMA table_info({quote(table)})").fetchall()
    keys = sorted(((row[5], row[1]) for row in info if row[5]), key=lambda p: p[0])
    return [name for _, name in keys], [row[1] for row in info if not row[5]]
