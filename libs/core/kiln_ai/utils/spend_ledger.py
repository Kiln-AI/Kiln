"""Per-conversation spend ledger for assistant-triggered operations.

The Kiln assistant triggers local operations (evals, data gen, task runs) via
its ``call_kiln_api`` tool; those operations run against the user's own model
providers and cost real money. This module tracks that spend per conversation
and enforces an optional user-set USD budget:

- ``current_conversation_id`` is set from the ``X-Kiln-Conversation-Id`` request
  header by the desktop server's middleware (and around assistant tool
  execution), so any model call made while handling an assistant-triggered
  request can be attributed to the conversation.
- The LiteLLM adapter calls :func:`record_spend` once per LLM call when the
  contextvar is set; calls with no LiteLLM-reported cost (local/custom models)
  debit nothing but are counted so the UI can surface "budget partially
  tracked".
- Budgets and running totals persist in ``~/.kiln_ai/conversation_budgets.json``
  so they survive app restarts. Conversations are client-minted uuid4 ids.

The budget number itself never blocks normal (user-initiated) UI operations:
nothing sets the contextvar outside assistant tool execution.
"""

import json
import math
import os
import re
import threading
import time
from contextvars import ContextVar

from pydantic import BaseModel

from kiln_ai.utils.config import Config

# Conversation id currently being served, set from the assistant's tool
# execution path / the desktop server's budget middleware. None outside
# assistant-triggered work.
current_conversation_id: ContextVar[str | None] = ContextVar(
    "kiln_current_conversation_id", default=None
)

# Header used by the assistant's call_kiln_api tool to attribute the local API
# requests it makes (and everything they spawn) to a conversation.
CONVERSATION_ID_HEADER = "X-Kiln-Conversation-Id"

# Client-minted conversation ids are lowercase uuid4 (mirrors the copilot
# backend's validation). ``\Z`` so a trailing newline can't pass the anchor.
_CONVERSATION_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)

# Entries untouched for this long are pruned on write; a conversation's budget
# is not meaningful long after the conversation itself is gone.
_PRUNE_AFTER_SECONDS = 90 * 24 * 60 * 60

_LEDGER_FILENAME = "conversation_budgets.json"

_lock = threading.Lock()


def is_valid_conversation_id(conversation_id: str) -> bool:
    return bool(_CONVERSATION_ID_PATTERN.match(conversation_id))


class BudgetStatus(BaseModel):
    conversation_id: str
    # None means spend is tracked but no cap is set.
    budget_usd: float | None = None
    spent_usd: float = 0.0
    # Model calls LiteLLM couldn't price (local/custom models). They debit
    # nothing, so when > 0 the budget is only partially tracked.
    unpriced_runs: int = 0
    unpriced_tokens: int = 0

    @property
    def remaining_usd(self) -> float | None:
        if self.budget_usd is None:
            return None
        return max(0.0, self.budget_usd - self.spent_usd)

    @property
    def exhausted(self) -> bool:
        return self.budget_usd is not None and self.spent_usd >= self.budget_usd


def _ledger_path() -> str:
    return os.path.join(Config.settings_dir(), _LEDGER_FILENAME)


def _load_ledger() -> dict[str, dict]:
    path = _ledger_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        # A corrupt ledger should never break assistant chat; better to lose
        # budget state than to hard-fail every tool call.
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _write_ledger(ledger: dict[str, dict]) -> None:
    now = time.time()
    pruned = {
        cid: entry
        for cid, entry in ledger.items()
        if now - float(entry.get("updated_at") or 0) < _PRUNE_AFTER_SECONDS
    }
    path = _ledger_path()
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(pruned, f, indent=2)
    os.replace(tmp_path, path)


def _entry_to_status(conversation_id: str, entry: dict) -> BudgetStatus:
    return BudgetStatus(
        conversation_id=conversation_id,
        budget_usd=entry.get("budget_usd"),
        spent_usd=float(entry.get("spent_usd") or 0.0),
        unpriced_runs=int(entry.get("unpriced_runs") or 0),
        unpriced_tokens=int(entry.get("unpriced_tokens") or 0),
    )


def set_budget(conversation_id: str, budget_usd: float | None) -> BudgetStatus:
    """Set (or clear, with None) the USD budget for a conversation.

    An absolute set: extending a budget means setting a new, larger total.
    Spend already recorded is preserved.
    """
    if not is_valid_conversation_id(conversation_id):
        raise ValueError(f"Invalid conversation id: {conversation_id[:80]!r}")
    if budget_usd is not None and (budget_usd < 0 or math.isnan(budget_usd)):
        raise ValueError("budget_usd must be a non-negative number")
    with _lock:
        ledger = _load_ledger()
        entry = ledger.get(conversation_id, {})
        entry["budget_usd"] = budget_usd
        entry["updated_at"] = time.time()
        ledger[conversation_id] = entry
        _write_ledger(ledger)
        return _entry_to_status(conversation_id, entry)


def record_spend(
    conversation_id: str,
    cost_usd: float | None,
    total_tokens: int | None,
) -> None:
    """Credit one model call's cost against the conversation.

    ``cost_usd=None`` (LiteLLM couldn't price the model) debits nothing but
    increments the unpriced counters so the UI can flag partial tracking.
    Recording works even before a budget is set, so a budget applied mid-way
    covers the conversation's full history.
    """
    if not is_valid_conversation_id(conversation_id):
        return
    with _lock:
        ledger = _load_ledger()
        entry = ledger.get(conversation_id, {})
        if cost_usd is not None and cost_usd > 0:
            entry["spent_usd"] = float(entry.get("spent_usd") or 0.0) + cost_usd
        elif cost_usd is None:
            entry["unpriced_runs"] = int(entry.get("unpriced_runs") or 0) + 1
            if total_tokens:
                entry["unpriced_tokens"] = (
                    int(entry.get("unpriced_tokens") or 0) + total_tokens
                )
        entry["updated_at"] = time.time()
        ledger[conversation_id] = entry
        _write_ledger(ledger)


def get_status(conversation_id: str) -> BudgetStatus | None:
    """The conversation's budget status, or None if nothing was ever recorded."""
    if not is_valid_conversation_id(conversation_id):
        return None
    with _lock:
        entry = _load_ledger().get(conversation_id)
    if entry is None:
        return None
    return _entry_to_status(conversation_id, entry)


def is_exhausted(conversation_id: str | None) -> bool:
    """True only when the conversation has a budget set and it is spent.

    None / unknown conversations and conversations without a budget are never
    exhausted — the feature is strictly opt-in.
    """
    if conversation_id is None:
        return False
    status = get_status(conversation_id)
    return status is not None and status.exhausted


def record_spend_for_current_conversation(
    cost_usd: float | None, total_tokens: int | None
) -> None:
    """Credit spend to the contextvar's conversation, if one is set.

    The single call site for adapters: a no-op outside assistant-triggered
    requests, and never raises (budget tracking must not break model calls).
    """
    conversation_id = current_conversation_id.get()
    if conversation_id is None:
        return
    try:
        record_spend(conversation_id, cost_usd, total_tokens)
    except Exception:
        # Deliberately swallow: ledger IO problems must not fail the run.
        pass
