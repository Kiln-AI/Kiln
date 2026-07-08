"""SubAgentRegistry unit tests (caps, wait, reports, cascades)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from .models import SubAgentSeed, SubAgentStatus, format_subagent_report
from .registry import SubAgentCapError, SubAgentRegistry
from .runner import SubAgentRunner


def _seed(parent_key: str = "trace:parent-1", name: str = "helper") -> SubAgentSeed:
    return SubAgentSeed(
        agent_type="general",
        name=name,
        prompt="Briefing.",
        parent_key=parent_key,
        parent_trace_id="parent-1",
    )


def _spawn(registry: SubAgentRegistry, seed: SubAgentSeed):
    return registry.spawn(seed, upstream_url="https://example.test", headers={})


@pytest.fixture
def hang_runner():
    """Patch the runner to hang until cancelled — tests drive lifecycle
    through the registry, not the network loop."""

    async def _hang(self) -> None:
        await asyncio.Event().wait()

    with patch.object(SubAgentRunner, "run", _hang):
        yield


async def test_per_parent_cap(hang_runner):
    registry = SubAgentRegistry(max_concurrent=10, max_per_parent=2)
    _spawn(registry, _seed())
    _spawn(registry, _seed())
    with pytest.raises(SubAgentCapError, match="2 running sub-agents"):
        _spawn(registry, _seed())
    # A different parent is unaffected.
    _spawn(registry, _seed(parent_key="trace:other"))
    for record in registry.list_all():
        await registry.stop(record.subagent_id)


async def test_global_cap(hang_runner):
    registry = SubAgentRegistry(max_concurrent=2, max_per_parent=5)
    _spawn(registry, _seed())
    _spawn(registry, _seed(parent_key="trace:other"))
    with pytest.raises(SubAgentCapError, match="Too many concurrent sub-agents"):
        _spawn(registry, _seed(parent_key="trace:third"))
    for record in registry.list_all():
        await registry.stop(record.subagent_id)


async def test_stop_sets_terminal_and_synthesizes_report(hang_runner):
    registry = SubAgentRegistry()
    record = _spawn(registry, _seed())
    assert await registry.stop(record.subagent_id) == "stopped"
    run = registry.get(record.subagent_id)
    assert run is not None
    assert run.record.status == SubAgentStatus.STOPPED
    assert "STOPPED" in (run.record.final_report or "")
    assert await registry.stop(record.subagent_id) == "already_finished"
    assert await registry.stop("sa_missing") == "not_found"


async def test_wait_returns_on_terminal_and_timeout(hang_runner):
    registry = SubAgentRegistry()
    done = _spawn(registry, _seed(name="fast"))
    slow = _spawn(registry, _seed(parent_key="trace:other", name="slow"))
    await registry.stop(done.subagent_id)

    records, timed_out = await registry.wait(
        [done.subagent_id, slow.subagent_id], timeout_seconds=0.05
    )
    assert {r.subagent_id for r in records} == {done.subagent_id, slow.subagent_id}
    assert timed_out == [slow.subagent_id]
    # Terminal record's report counts as delivered via the wait result.
    assert registry.get(done.subagent_id).record.report_delivered is True
    await registry.stop(slow.subagent_id)


async def test_interactive_parent_report_queued_and_drained(hang_runner):
    registry = SubAgentRegistry()
    parent_key = registry.parent_key_for_trace("leaf-1")
    record = _spawn(registry, _seed(parent_key=parent_key))
    await registry.stop(record.subagent_id)

    # The parent's leaf rotates; the alias chain keeps the key reachable.
    registry.note_parent_trace("leaf-1", "leaf-2")
    reports = registry.pending_reports_for_trace("leaf-2")
    assert len(reports) == 1
    assert f'id="{record.subagent_id}"' in reports[0]
    assert 'status="stopped"' in reports[0]
    # Drained exactly once.
    assert registry.pending_reports_for_trace("leaf-2") == []


async def test_auto_parent_report_injected_via_auto_registry(hang_runner):
    registry = SubAgentRegistry()
    parent_key = registry.parent_key_for_auto_run("ar_123")
    record = _spawn(registry, _seed(parent_key=parent_key))

    with patch(
        "app.desktop.studio_server.chat.auto.registry.auto_chat_registry.send_message",
        return_value=True,
    ) as mock_send:
        await registry.stop(record.subagent_id)

    mock_send.assert_called_once()
    run_id, message = mock_send.call_args.args
    assert run_id == "ar_123"
    assert f'id="{record.subagent_id}"' in message.content
    assert registry.get(record.subagent_id).record.report_delivered is True


async def test_auto_parent_gone_falls_back_to_queue(hang_runner):
    registry = SubAgentRegistry()
    parent_key = registry.parent_key_for_auto_run("ar_gone")
    record = _spawn(registry, _seed(parent_key=parent_key))
    with patch(
        "app.desktop.studio_server.chat.auto.registry.auto_chat_registry.send_message",
        return_value=False,
    ):
        await registry.stop(record.subagent_id)
    assert registry.has_pending_reports(parent_key)
    assert registry.get(record.subagent_id).record.report_delivered is False


async def test_consent_memory_survives_leaf_rotation(hang_runner):
    registry = SubAgentRegistry()
    key = registry.parent_key_for_trace("leaf-1")
    registry.mark_consented(key)
    registry.note_parent_trace("leaf-1", "leaf-2")
    assert registry.parent_key_for_trace("leaf-2") == key
    assert registry.is_consented(registry.parent_key_for_trace("leaf-2"))


async def test_stop_children_cascade(hang_runner):
    registry = SubAgentRegistry()
    parent_key = registry.parent_key_for_trace("leaf-1")
    a = _spawn(registry, _seed(parent_key=parent_key, name="a"))
    b = _spawn(registry, _seed(parent_key=parent_key, name="b"))
    other = _spawn(registry, _seed(parent_key="trace:other", name="c"))

    stopped = await registry.stop_children(parent_key)
    assert stopped == 2
    assert registry.get(a.subagent_id).record.status == SubAgentStatus.STOPPED
    assert registry.get(b.subagent_id).record.status == SubAgentStatus.STOPPED
    assert registry.get(other.subagent_id).record.status == SubAgentStatus.RUNNING
    # Pending reports for that parent are dropped.
    assert not registry.has_pending_reports(parent_key)
    await registry.stop(other.subagent_id)


async def test_handle_session_deleted_stops_parent_children_and_child(hang_runner):
    registry = SubAgentRegistry()
    parent_key = registry.parent_key_for_trace("leaf-1")
    child = _spawn(registry, _seed(parent_key=parent_key))
    # Simulate the child's own session trace becoming known.
    registry._on_trace(child.subagent_id, "child-leaf-1")

    # Deleting the parent session stops its children.
    await registry.handle_session_deleted("leaf-1")
    assert registry.get(child.subagent_id).record.status == SubAgentStatus.STOPPED

    # Deleting a child session stops that child (fresh registry).
    registry2 = SubAgentRegistry()
    child2 = _spawn(registry2, _seed())
    registry2._on_trace(child2.subagent_id, "child2-leaf")
    await registry2.handle_session_deleted("child2-leaf")
    assert registry2.get(child2.subagent_id).record.status == SubAgentStatus.STOPPED


async def test_format_subagent_report_escapes_title(hang_runner):
    registry = SubAgentRegistry()
    record = _spawn(registry, _seed(name='evil "title" <x>'))
    await registry.stop(record.subagent_id)
    frame = format_subagent_report(registry.get(record.subagent_id).record)
    assert "&quot;title&quot;" in frame
    assert "<x>" not in frame.split("\n")[0]


async def test_subagent_for_trace_join(hang_runner):
    registry = SubAgentRegistry()
    record = _spawn(registry, _seed())
    registry._on_trace(record.subagent_id, "child-leaf")
    found = registry.subagent_for_trace("child-leaf")
    assert found is not None and found.subagent_id == record.subagent_id
    assert registry.subagent_for_trace("unknown") is None
    await registry.stop(record.subagent_id)
