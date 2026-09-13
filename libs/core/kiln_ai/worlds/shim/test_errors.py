from __future__ import annotations

import sys

import pytest

from .errors import (
    ArgumentError,
    DbError,
    SeahavenError,
    ToolError,
    UnknownTool,
    WorldBug,
    WorldGap,
)

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)


@pytest.mark.parametrize(
    "error, expected",
    [
        (
            ToolError("not_found", "no item 7", {"id": 7}),
            {"code": "not_found", "message": "no item 7", "details": {"id": 7}},
        ),
        (
            ArgumentError(
                "add", [{"path": "name", "message": "required", "type": "missing"}]
            ),
            {
                "code": "invalid_arguments",
                "message": "invalid arguments: name: required",
                "details": [{"path": "name", "message": "required", "type": "missing"}],
            },
        ),
        (
            DbError("no such table: items", sqlite_code=1),
            {"code": "db_error", "message": "database error", "details": None},
        ),
        (
            DbError("not authorized", refusals=("writes",)),
            {"code": "db_error", "message": "not allowed: writes", "details": None},
        ),
        (
            UnknownTool("dance"),
            {"code": "unknown_tool", "message": "unknown tool: dance", "details": None},
        ),
        (
            WorldGap("archive_item"),
            {
                "code": "world_gap",
                "message": "not implemented in this world",
                "details": {"operation": "archive_item"},
            },
        ),
    ],
)
def test_to_dict_shapes(error, expected):
    assert error.to_dict() == expected


def test_str_is_message_and_repr_shows_fields():
    error = ToolError("not_found", "no item 7", {"id": 7})
    assert str(error) == "no item 7"
    assert "not_found" in repr(error) and "{'id': 7}" in repr(error)
    assert "no such table" in repr(DbError("no such table: items"))


def test_argument_error_message_joins_violations():
    error = ArgumentError(
        "add",
        [
            {"path": "name", "message": "required", "type": "missing"},
            {"path": "count", "message": "not an int", "type": "int_type"},
        ],
    )
    assert error.message == "invalid arguments: name: required; count: not an int"
    assert error.tool == "add"
    assert error.details == error.violations


def test_db_error_default_message_hides_sqlite_text():
    error = DbError("no such column: secret_column", sqlite_code=1)
    assert error.message == "database error"
    assert "secret_column" not in error.message
    assert error.sqlite_message == "no such column: secret_column"
    assert error.sqlite_code == 1
    assert error.refusals == ()


def test_world_gap_code_and_default_details():
    assert WorldGap("x").details == {"operation": "x"}
    custom = WorldGap("x", "gone", {"http_status": 501})
    assert custom.message == "gone" and custom.details == {"http_status": 501}
    assert custom.operation == "x"


def test_hierarchy():
    assert issubclass(WorldBug, SeahavenError)
    assert issubclass(ToolError, SeahavenError)
    assert not issubclass(WorldBug, ToolError)
    assert not issubclass(ToolError, WorldBug)
    for subclass in (ArgumentError, DbError, UnknownTool, WorldGap):
        assert issubclass(subclass, ToolError)
