"""Interceptor chain unit tests + drift guards.

The runtime deliberately keeps canonical COPIES of constants whose old homes
are deleted phase by phase, and the guard style below tracks that lifecycle:

- ``chat/subagents/`` was deleted in phase 2 and ``chat/auto/`` in phase 3,
  so ALL the guards are now BYTE-PINS of the exact strings — the runtime is
  their only home, and the pinned bytes are persisted in traces, so silently
  changing one corrupts the protocol.

An intentional change must update the pin here AND the golden fixtures
(these strings ride the captured upstream request bodies)."""

from __future__ import annotations

import json

from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent

from .interceptors import (
    AUTO_INTERCEPTORS,
    AUTO_MODE_NOOP_RESULT,
    DEPTH_LIMIT_RESULT,
    ENABLE_AUTO_MODE_RESULT,
    INTERACTIVE_INTERCEPTORS,
    ORCHESTRATION_TOOL_NAMES,
    SPAWN_SUBAGENT_TOOL_NAME,
    SUBAGENT_INTERCEPTORS,
    InterceptContext,
    intercept_auto_mode_signals_noop,
    intercept_disable_auto_mode_interactive,
    intercept_disable_auto_mode_terminal,
    intercept_enable_auto_mode_consent,
    intercept_enable_auto_mode_noop,
    intercept_orchestration_depth_guard,
)
from .models import (
    ConversationRecord,
    auto_policy,
    interactive_policy,
    subagent_policy,
    SubAgentSeed,
)


def _event(name: str, tc_id: str = "tc1", input: dict | None = None):
    return ToolInputAvailableEvent(toolCallId=tc_id, toolName=name, input=input or {})


def _ctx(policy, kind="interactive", events=None):
    return InterceptContext(
        record=ConversationRecord(kind=kind),
        policy=policy,
        client_events=events or [],
    )


# ── Drift guards ───────────────────────────────────────────────────────────────
#
# Phase-1 note: these started as equality checks against the OLD modules
# (chat/subagents/*, chat/auto/runner.py). Phases 2–3 deleted both old homes,
# making the runtime the CANONICAL (and only) home of these strings — every
# assertion below therefore pins the exact bytes, because each string is
# persisted in traces (tool results, message framings, kickoff text, report
# frames) and silently changing one would corrupt the protocol contract the
# golden fixtures also pin.


class TestDriftGuards:
    def test_orchestration_tool_names_match_backend_contract(self):
        # Must match the backend's client-visible tool schemas
        # (kiln_server tools/subagent_tools.py). The relocated executor
        # (chat/orchestration.py) imports these same objects, so it can't
        # drift separately.
        from app.desktop.studio_server.chat import orchestration

        assert ORCHESTRATION_TOOL_NAMES == {
            "spawn_subagent",
            "get_subagent_status",
            "wait_for_subagents",
            "stop_subagent",
        }
        assert orchestration.ORCHESTRATION_TOOL_NAMES == ORCHESTRATION_TOOL_NAMES
        assert orchestration.SPAWN_SUBAGENT_TOOL_NAME == SPAWN_SUBAGENT_TOOL_NAME

    def test_result_constants_pinned(self):
        # Persisted-in-trace strings, pinned as exact bytes: the sub-agent
        # constants since phase 2, ENABLE since phase 3 deleted its old home
        # (chat/auto/runner.py).
        assert ENABLE_AUTO_MODE_RESULT == (
            '{"status": "enabled", "detail": "Auto mode is already enabled."}'
        )
        assert (
            DEPTH_LIMIT_RESULT
            == '{"error": "Sub-agents cannot spawn or manage sub-agents."}'
        )
        assert AUTO_MODE_NOOP_RESULT == (
            '{"status": "noop", "detail": "This session already runs '
            'autonomously; auto mode does not apply."}'
        )

    def test_framing_reminders_pinned(self):
        from .engine import SIDE_NOTE_REMINDER, STEER_REMINDER

        # Old homes (chat/auto/runner.py, chat/subagents/runner.py) deleted
        # in phases 3 and 2 respectively — pin the exact persisted bytes.
        assert SIDE_NOTE_REMINDER == (
            "<system-reminder>"
            "This message arrived from the user while you are working autonomously "
            "in auto mode. Treat it as a side note: weave any acknowledgment or "
            "answer into your ongoing work and keep going in the same turn — do not "
            "end your turn just to reply. Stop only if the message explicitly asks "
            "you to, or your task is already complete."
            "</system-reminder>"
        )
        assert STEER_REMINDER == (
            "<system-reminder>"
            "This message was sent by the user overseeing your background run. "
            "Incorporate the guidance and continue working in the same turn — do not "
            "end your turn just to reply. End only when your job (as adjusted) is done, "
            "with your final report."
            "</system-reminder>"
        )

    def test_kickoff_and_seed_body_pinned(self):
        # Byte-for-byte pin of the old SubAgentRunner's kickoff/_build_seed_body
        # (deleted in phase 2); also covered end-to-end by the
        # subagent_seed_and_steer golden fixture.
        from .models import build_subagent_seed_body, kickoff_message

        assert kickoff_message("n", "p") == (
            "n — your assignment:\n\np\n\n"
            "Begin now, work autonomously, and end with your final report."
        )
        assert build_subagent_seed_body(
            SubAgentSeed(
                agent_type="general", name="n", prompt="p", parent_trace_id="pt"
            )
        ) == {
            "messages": [{"role": "user", "content": kickoff_message("n", "p")}],
            "agent": {
                "agent_type": "general",
                "seed_prompt": "p",
                "parent_trace_id": "pt",
            },
            "auto_mode": True,
        }

    def test_report_frame_pinned_and_escapes_title(self):
        # The frame shape is parsed by the client's report-panel detection AND
        # persisted in parent traces; the id attribute carries the child's
        # session id since phase 2 (an opaque handle to the client, exactly
        # like the old sa_ id).
        from .models import RunState, format_subagent_report

        record = ConversationRecord(
            kind="subagent",
            name='evil "title" <x>',
            agent_type="general",
            state=RunState.COMPLETED,
            final_report="All done.",
        )
        assert format_subagent_report(record) == (
            f'<subagent_report id="{record.session_id}" '
            'agent_type="general" status="completed" '
            'title="evil &quot;title&quot; &lt;x>">\n'
            "All done.\n"
            "</subagent_report>"
        )


# ── Chain composition (priority order preserved from the old scans) ───────────


def test_chain_order_matches_old_scan_priority():
    assert INTERACTIVE_INTERCEPTORS == (
        intercept_enable_auto_mode_consent,
        intercept_disable_auto_mode_interactive,
    )
    assert AUTO_INTERCEPTORS == (
        intercept_disable_auto_mode_terminal,
        intercept_enable_auto_mode_noop,
    )
    assert SUBAGENT_INTERCEPTORS == (
        intercept_orchestration_depth_guard,
        intercept_auto_mode_signals_noop,
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
        assert payload["enable_tool_call_id"] == "tc_e"
        assert payload["reason"] == "lots to do"
        # Phase 5: the consent event carries NO trace_id — accept/decline is
        # keyed by session id (functional spec §4).
        assert "trace_id" not in payload
        assert [s["toolCallId"] for s in payload["sibling_tool_calls"]] == ["tc_s"]

    def test_passes_other_tools(self):
        ctx = _ctx(interactive_policy())
        assert intercept_enable_auto_mode_consent(_event("add"), ctx) is None


class TestDisable:
    def test_interactive_is_immediate_resolve_with_flag_clear(self):
        res = intercept_disable_auto_mode_interactive(
            _event("disable_auto_mode"), _ctx(interactive_policy())
        )
        assert res is not None and res.kind == "resolve_immediate"
        assert res.clear_auto_flag is True
        assert json.loads(res.result_json or "") == {"status": "disabled"}

    def test_auto_is_terminal_resolve_with_flag_clear(self):
        res = intercept_disable_auto_mode_terminal(
            _event("disable_auto_mode"), _ctx(auto_policy(), kind="auto")
        )
        assert res is not None and res.kind == "resolve_terminal"
        assert res.clear_auto_flag is True

    def test_passes_other_tools(self):
        assert (
            intercept_disable_auto_mode_interactive(
                _event("add"), _ctx(interactive_policy())
            )
            is None
        )


class TestChildInterceptors:
    def _child_policy(self):
        return subagent_policy(SubAgentSeed(agent_type="general", name="n", prompt="p"))

    def test_depth_guard_rejects_orchestration_calls(self):
        policy = self._child_policy()
        for name in ORCHESTRATION_TOOL_NAMES:
            res = intercept_orchestration_depth_guard(
                _event(name), _ctx(policy, kind="subagent")
            )
            assert res is not None and res.result_json == DEPTH_LIMIT_RESULT

    def test_depth_guard_passes_at_depth_zero(self):
        # Parent conversations execute orchestration calls for real (via
        # execute_tool_batch's dispatch) — the guard is depth-1 only.
        res = intercept_orchestration_depth_guard(
            _event("spawn_subagent"), _ctx(interactive_policy())
        )
        assert res is None

    def test_auto_signals_resolve_as_noops(self):
        policy = self._child_policy()
        for name in ("enable_auto_mode", "disable_auto_mode"):
            res = intercept_auto_mode_signals_noop(
                _event(name), _ctx(policy, kind="subagent")
            )
            assert res is not None and res.result_json == AUTO_MODE_NOOP_RESULT


def test_enable_noop_resolves_already_enabled():
    res = intercept_enable_auto_mode_noop(
        _event("enable_auto_mode"), _ctx(auto_policy(), kind="auto")
    )
    assert res is not None and res.kind == "resolve"
    assert res.result_json == ENABLE_AUTO_MODE_RESULT
