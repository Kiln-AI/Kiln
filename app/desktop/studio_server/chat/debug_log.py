"""Forensic debug logging for the assistant runtime (desktop side).

Enabled with the ``KILN_CHAT_DEBUG_LOG`` environment variable: ``1``/``true``
logs to ``<settings>/logs/kiln_chat_debug.jsonl``; any other non-empty value
is used as the target file path. Each event is one JSON line carrying ids and
timings — never message content — keyed by the conversation ``session_id``
(``cv_…``). The desktop sends that same id upstream on every request as
``X-Kiln-Conversation-Id``, and kiln_server's ``chat_debug_log_enabled`` flag
logs it on its side, so the two timelines can be joined per conversation when
investigating a stuck or misbehaving assistant conversation.

This is a local debugging tool: writes are synchronous appends under a
process-wide lock and the file grows unbounded while the flag is set.
"""

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kiln_ai.utils.config import Config

ENV_VAR = "KILN_CHAT_DEBUG_LOG"
_FALSY = frozenset(["", "0", "false", "no", "off"])
_TRUTHY_DEFAULT_PATH = frozenset(["1", "true", "yes", "on"])

_write_lock = threading.Lock()
_process_started = time.monotonic()


def chat_debug_enabled() -> bool:
    return os.getenv(ENV_VAR, "").strip().lower() not in _FALSY


def _target_path() -> Path:
    value = os.getenv(ENV_VAR, "").strip()
    if value.lower() in _TRUTHY_DEFAULT_PATH:
        return Path(Config.settings_dir()) / "logs" / "kiln_chat_debug.jsonl"
    return Path(value)


def chat_debug_log(
    event: str, conversation_id: str | None = None, **fields: Any
) -> None:
    """Append one JSONL debug event; a no-op unless the env flag is set.

    ``elapsed_ms`` is process-relative (a shared monotonic clock) so gaps
    between events are readable without timestamp arithmetic.
    """
    if not chat_debug_enabled():
        return
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "elapsed_ms": round((time.monotonic() - _process_started) * 1000, 1),
        "event": event,
        "conversation_id": conversation_id,
        **fields,
    }
    line = json.dumps(record, default=str, ensure_ascii=False)
    # Debug-only tool: a failed write must never affect the runtime.
    try:
        path = _target_path()
        with _write_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError:
        pass
