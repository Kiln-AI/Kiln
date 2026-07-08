"""Interceptor chain unit tests + drift guards.

The runtime deliberately keeps canonical COPIES of constants whose old homes
(chat/auto/, chat/subagents/) are deleted in later phases. While both copies
exist, the drift tests here pin them equal — an intentional change must
update both (and the golden fixtures, since these strings are persisted in
traces)."""

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


def _ctx(policy, kind="interactive", events=None, trace_id="tr-1"):
    return InterceptContext(
        record=ConversationRecord(kind=kind),
        policy=policy,
        trace_id=trace_id,
        client_events=events or [],
    )


# ── Drift guards against the old (doomed) modules ─────────────────────────────


class TestDriftAgainstOldModules:
    def test_orchestration_tool_names_match_orchestration_module(self):
        # interceptors.py keeps a literal copy to stay decoupled from the old
        # registries; it must track the orchestration module (which itself
        # must match the backend tool schemas) until phase 2 unifies them.
        from app.desktop.studio_server.chat.subagents import orchestration

        assert ORCHESTRATION_TOOL_NAMES == orchestration.ORCHESTRATION_TOOL_NAMES
        assert SPAWN_SUBAGENT_TOOL_NAME == orchestration.SPAWN_SUBAGENT_TOOL_NAME

    def test_result_constants_match_old_runners(self):
        # These strings are persisted in traces — the copies must stay
        # byte-identical to the old runners' until those are deleted.
        from app.desktop.studio_server.chat.auto import runner as auto_runner
        from app.desktop.studio_server.chat.subagents import runner as sub_runner

        assert ENABLE_AUTO_MODE_RESULT == auto_runner.ENABLE_AUTO_MODE_RESULT
        assert DEPTH_LIMIT_RESULT == sub_runner.DEPTH_LIMIT_RESULT
        assert AUTO_MODE_NOOP_RESULT == sub_runner.AUTO_MODE_NOOP_RESULT

    def test_framing_reminders_match_old_runners(self):
        from app.desktop.studio_server.chat.auto import runner as auto_runner
        from app.desktop.studio_server.chat.subagents import runner as sub_runner

        from .engine import SIDE_NOTE_REMINDER, STEER_REMINDER

        assert SIDE_NOTE_REMINDER == auto_runner._SIDE_NOTE_REMINDER
        assert STEER_REMINDER == sub_runner._STEER_REMINDER

    def test_kickoff_and_seed_body_match_old_subagent_runner(self):
        from app.desktop.studio_server.chat.subagents.models import (
            SubAgentSeed as OldSeed,
        )
        from app.desktop.studio_server.chat.subagents.runner import (
            SubAgentRunner,
            _kickoff_message,
        )

        from .models import build_subagent_seed_body, kickoff_message

        assert kickoff_message("n", "p") == _kickoff_message("n", "p")
        new = build_subagent_seed_body(
            SubAgentSeed(
                agent_type="general", name="n", prompt="p", parent_trace_id="pt"
            )
        )
        old_runner = SubAgentRunner(
            subagent_id="sa_x",
            seed=OldSeed(
                agent_type="general",
                name="n",
                prompt="p",
                parent_key="trace:pt",
                parent_trace_id="pt",
            ),
            upstream_url="https://example.test",
            headers={},
            emit=lambda b: None,
        )
        assert new == old_runner._build_seed_body()

    def test_report_frame_matches_old_formatter(self):
        from app.desktop.studio_server.chat.subagents.models import (
            SubAgentRecord,
            SubAgentStatus,
            format_subagent_report as old_format,
        )

        from .models import RunState, format_subagent_report

        record = ConversationRecord(
            kind="subagent",
            name='evil "title" <x>',
            agent_type="general",
            state=RunState.COMPLETED,
            final_report="All done.",
        )
        old_record = SubAgentRecord(
            subagent_id=record.session_id,  # align ids so frames compare 1:1
            name='evil "title" <x>',
            agent_type="general",
            status=SubAgentStatus.COMPLETED,
            parent_key="trace:parent",  # frame doesn't include it
            final_report="All done.",
        )
        assert format_subagent_report(record) == old_format(old_record)


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
        assert payload["trace_id"] == "tr-1"
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
