import json
from pathlib import Path

import pytest

from app.desktop.studio_server.chat.debug_log import (
    ENV_VAR,
    chat_debug_enabled,
    chat_debug_log,
)


@pytest.fixture
def log_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "chat_debug.jsonl"
    monkeypatch.setenv(ENV_VAR, str(target))
    return target


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert not chat_debug_enabled()
    chat_debug_log("anything", conversation_id="cv_x")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "FALSE"])
def test_falsy_values_disable(monkeypatch: pytest.MonkeyPatch, value: str):
    monkeypatch.setenv(ENV_VAR, value)
    assert not chat_debug_enabled()


def test_writes_jsonl_events_to_explicit_path(log_file: Path):
    assert chat_debug_enabled()
    chat_debug_log("run_started", conversation_id="cv_abc", kind="interactive")
    chat_debug_log("inbox_injected", conversation_id="cv_abc", count=2)

    lines = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert [e["event"] for e in lines] == ["run_started", "inbox_injected"]
    assert all(e["conversation_id"] == "cv_abc" for e in lines)
    assert lines[0]["kind"] == "interactive"
    assert lines[1]["count"] == 2
    assert all("ts" in e and "elapsed_ms" in e for e in lines)


def test_truthy_value_uses_default_settings_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv(ENV_VAR, "1")
    monkeypatch.setattr(
        "app.desktop.studio_server.chat.debug_log.Config.settings_dir",
        classmethod(lambda cls, create=True: str(tmp_path)),
    )
    chat_debug_log("run_started", conversation_id="cv_abc")
    default_file = tmp_path / "logs" / "kiln_chat_debug.jsonl"
    assert default_file.exists()
    assert json.loads(default_file.read_text())["event"] == "run_started"


def test_write_failure_never_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("occupied")
    # Target "directory" is a plain file: mkdir/open raise OSError internally.
    monkeypatch.setenv(ENV_VAR, str(blocker / "chat_debug.jsonl"))
    chat_debug_log("event", conversation_id="cv_x")
