"""Interceptor chain unit tests + byte pins.

The pinned strings are persisted in traces (tool results, message framings),
so silently changing one corrupts the protocol. An intentional change must
update the pin here AND the golden fixtures (these strings ride the captured
upstream request bodies)."""

from __future__ import annotations

import json

from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent

from .interceptors import (
    AUTO_INTERCEPTORS,
    DISABLE_AUTO_MODE_STALE_RESULT,
    ENABLE_AUTO_MODE_RESULT,
    INTERACTIVE_INTERCEPTORS,
    InterceptContext,
    intercept_disable_auto_mode_stale,
    intercept_enable_auto_mode_consent,
    intercept_enable_auto_mode_noop,
)
from .models import ConversationRecord, auto_policy, interactive_policy


def _event(name: str, tc_id: str = "tc1", input: dict | None = None):
    return ToolInputAvailableEvent(toolCallId=tc_id, toolName=name, input=input or {})


def _ctx(policy, kind="interactive", events=None, record=None):
    return InterceptContext(
        record=record or ConversationRecord(kind=kind),
        policy=policy,
        client_events=events or [],
    )


# ── Byte pins ─────────────────────────────────────────────────────────────────


class TestPinnedStrings:
    def test_result_constants_pinned(self):
        assert ENABLE_AUTO_MODE_RESULT == (
            '{"status": "enabled", "detail": "Auto mode is already enabled."}'
        )
        # FR1 stale-disable refusal — persisted in traces (and doubling as
        # the model's pointer to the Stop button), so pinned byte-for-byte.
        assert DISABLE_AUTO_MODE_STALE_RESULT == (
            '{"status": "not_available", "message": "Auto mode can only be '
            'turned off by the user (Stop button)."}'
        )

    def test_side_note_reminder_pinned(self):
        from .engine import SIDE_NOTE_REMINDER

        assert SIDE_NOTE_REMINDER == (
            "<system-reminder>"
            "This message arrived from the user while you are working autonomously "
            "in auto mode. Treat it as a side note: weave any acknowledgment or "
            "answer into your ongoing work and keep going in the same turn — do not "
            "end your turn just to reply. Stop only if the message explicitly asks "
            "you to, or your task is already complete."
            "</system-reminder>"
        )


# ── Chain composition ─────────────────────────────────────────────────────────


def test_chain_order_is_priority():
    # Consent leads the interactive chain (it must outrank the approval
    # gate); both chains end in the FR1 stale-disable backstop.
    assert INTERACTIVE_INTERCEPTORS == (
        intercept_enable_auto_mode_consent,
        intercept_disable_auto_mode_stale,
    )
    assert AUTO_INTERCEPTORS == (
        intercept_enable_auto_mode_noop,
        intercept_disable_auto_mode_stale,
    )


# ── Individual interceptors ───────────────────────────────────────────────────


class TestEnableConsent:
    def test_builds_consent_control_event_with_siblings(self):
        enable = _event("enable_auto_mode", "tc_e", {"reason": "lots to do"})
        sibling = _event("add", "tc_s", {"a": 1, "b": 2})
        ctx = _ctx(interactive_policy(), events=[enable, sibling])
        res = intercept_enable_auto_mode_consent(enable, ctx)
        assert res is not None and res.kind == "control"
        assert res.control_bytes is not None
        payload = json.loads(res.control_bytes.decode()[6:])
        assert payload["type"] == "auto-mode-consent-required"
        assert payload["trigger"] == "enable_auto_mode"
        assert payload["gating_tool_call_id"] == "tc_e"
        assert payload["enable_tool_call_id"] == "tc_e"
        assert payload["reason"] == "lots to do"
        # The consent event carries NO trace_id — accept/decline is keyed by
        # session id (functional spec §4).
        assert "trace_id" not in payload
        assert [s["toolCallId"] for s in payload["sibling_tool_calls"]] == ["tc_s"]

    def test_passes_other_tools(self):
        ctx = _ctx(interactive_policy())
        assert intercept_enable_auto_mode_consent(_event("add"), ctx) is None


class TestDisableStale:
    # FR1: disable_auto_mode is not offered upstream; a stale call is a PLAIN
    # refusal resolve — never a takeover, never a flag mutation — so the
    # burst/turn continues.

    def test_interactive_chain_refuses_without_side_effects(self):
        res = intercept_disable_auto_mode_stale(
            _event("disable_auto_mode"), _ctx(interactive_policy())
        )
        assert res is not None and res.kind == "resolve"
        assert res.result_json == DISABLE_AUTO_MODE_STALE_RESULT

    def test_auto_chain_refuses_without_side_effects(self):
        res = intercept_disable_auto_mode_stale(
            _event("disable_auto_mode"), _ctx(auto_policy(), kind="auto")
        )
        assert res is not None and res.kind == "resolve"
        assert res.result_json == DISABLE_AUTO_MODE_STALE_RESULT

    def test_passes_other_tools(self):
        assert (
            intercept_disable_auto_mode_stale(_event("add"), _ctx(interactive_policy()))
            is None
        )


def test_enable_noop_resolves_already_enabled():
    res = intercept_enable_auto_mode_noop(
        _event("enable_auto_mode"), _ctx(auto_policy(), kind="auto")
    )
    assert res is not None and res.kind == "resolve"
    assert res.result_json == ENABLE_AUTO_MODE_RESULT
