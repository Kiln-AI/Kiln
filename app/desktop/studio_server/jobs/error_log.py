from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

ERROR_LOG_DIR_NAME = "kiln_jobs"


def error_log_dir() -> Path:
    return Path(tempfile.gettempdir()) / ERROR_LOG_DIR_NAME


def error_log_path(run_id: str) -> Path:
    return error_log_dir() / f"{run_id}.json"


def append_error(run_id: str, entry: dict[str, Any]) -> None:
    """Append a single error entry to this run's log (JSON Lines). Best-effort.

    Creates the directory lazily. Any IO/serialization failure is swallowed —
    the error log is a diagnostic convenience, never a guarantee.
    """
    try:
        directory = error_log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False)
        with error_log_path(run_id).open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_errors(run_id: str) -> list[dict[str, Any]]:
    """Read the error log for a run as a list of objects. Best-effort.

    A missing or unreadable file returns []. Individual unparsable lines are
    skipped rather than failing the whole read. Never raises.
    """
    entries: list[dict[str, Any]] = []
    try:
        path = error_log_path(run_id)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    entries.append(parsed)
    except Exception:
        return entries
    return entries


def delete_errors(run_id: str) -> None:
    """Best-effort remove the error log file for a run. Swallows all errors."""
    try:
        error_log_path(run_id).unlink(missing_ok=True)
    except Exception:
        pass
