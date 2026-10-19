from __future__ import annotations

import uuid

import pytest

from app.desktop.studio_server.jobs import error_log


@pytest.fixture
def run_id(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.desktop.studio_server.jobs.error_log.tempfile.gettempdir",
        lambda: str(tmp_path),
    )
    return str(uuid.uuid4())


def test_append_and_read_round_trip(run_id):
    error_log.append_error(run_id, {"error_message": "first", "step": 1})
    error_log.append_error(run_id, {"error_message": "second", "item_id": "x"})

    entries = error_log.read_errors(run_id)
    assert entries == [
        {"error_message": "first", "step": 1},
        {"error_message": "second", "item_id": "x"},
    ]


def test_read_missing_file_returns_empty(run_id):
    assert error_log.read_errors(run_id) == []


def test_read_skips_unparsable_lines(run_id):
    error_log.append_error(run_id, {"error_message": "good"})
    with error_log.error_log_path(run_id).open("a", encoding="utf-8") as f:
        f.write("not json at all\n")
        f.write("\n")
    error_log.append_error(run_id, {"error_message": "also good"})

    entries = error_log.read_errors(run_id)
    assert entries == [
        {"error_message": "good"},
        {"error_message": "also good"},
    ]


def test_delete_removes_file(run_id):
    error_log.append_error(run_id, {"error_message": "x"})
    assert error_log.error_log_path(run_id).exists()

    error_log.delete_errors(run_id)
    assert not error_log.error_log_path(run_id).exists()
    assert error_log.read_errors(run_id) == []


def test_delete_missing_file_is_noop(run_id):
    error_log.delete_errors(run_id)
    assert error_log.read_errors(run_id) == []


def test_append_never_raises_on_bad_dir(monkeypatch, run_id):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("app.desktop.studio_server.jobs.error_log.Path.mkdir", boom)
    error_log.append_error(run_id, {"error_message": "swallowed"})
