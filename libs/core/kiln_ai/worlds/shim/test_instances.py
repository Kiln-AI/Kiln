from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from . import instances as instances_module
from .conftest import FIXED_NOW, build_toy_world
from .ctx import Ctx
from .errors import UnknownTool, WorldBug
from .instances import WORK_ROOT_NAME, set_concurrency_gate

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)

SLOW_SQL = """
WITH RECURSIVE counter(n) AS (
    SELECT 1 UNION ALL SELECT n + 1 FROM counter WHERE n < 400000
)
SELECT count(*) FROM counter
"""


@pytest.fixture
def hook_world(tmp_path):
    return build_toy_world(tmp_path, with_hook=True)


def test_blank_now_default_explicit_and_now_with_fixture_refused(toy_world, frozen):
    explicit = toy_world.instance(None, now=FIXED_NOW)
    default = toy_world.instance(None)
    try:
        assert explicit.clock.iso() == FIXED_NOW
        assert default.clock.iso() != FIXED_NOW
        assert default.clock.now().microsecond % 1000 == 0
    finally:
        explicit.destroy()
        default.destroy()
    with pytest.raises(WorldBug, match="blank instances only"):
        toy_world.instance("base", now=FIXED_NOW)


def test_fixture_id_path_separator_refused_before_fs(toy_world):
    with pytest.raises(WorldBug, match="single directory name"):
        toy_world.instance("../escape")
    assert not toy_world.fixtures_dir.exists()
    assert not toy_world.work_dir.exists()


def test_schema_hash_mismatch_message(tmp_path, frozen):
    other = build_toy_world(
        tmp_path / "other",
        fixtures_dir=frozen.dir.parent,
        work_dir=tmp_path / "other-work",
    )
    other.schema_hash = "deadbeef"
    with pytest.raises(WorldBug, match="different schema; regenerate it"):
        other.instance("base")


def test_seed_determinism_across_instances(toy_world, frozen):
    def ids(seed):
        instance = toy_world.instance("base", seed=seed)
        try:
            return [instance.call("add_item", name="x")["id"] for _ in range(3)]
        finally:
            instance.destroy()

    assert ids(7) == ids(7)
    assert ids(7) != ids(8)
    assert ids(None) != ids(7)


def test_unknown_startup_kwarg_refused_no_dir(hook_world):
    with pytest.raises(WorldBug, match=r"unknown reset argument\(s\): \['nonsense'\]"):
        hook_world.instance(None, nonsense=1)
    work_root = hook_world.work_dir
    assert not work_root.exists() or list(work_root.iterdir()) == []


def test_hooks_run_in_order_atomically_and_abort_removes_dir(tmp_path):
    order: list[str] = []
    world = build_toy_world(tmp_path, with_hook=True)

    @world.instance_startup
    def second(ctx: Ctx, *, owner: str = "nobody") -> None:
        order.append("second")
        ctx.db.execute("INSERT INTO items (id, name) VALUES ('h2', 'second')")

    instance = world.instance(None, owner="ada")
    try:
        assert order == ["second"]
        names = [r["id"] for r in instance.db.rows("SELECT id FROM items ORDER BY id")]
        assert names == ["h2", "seeded"]
        assert (
            instance.db.one("SELECT note FROM items WHERE id = 'seeded'")["note"]
            == "ada"
        )
    finally:
        instance.destroy()

    @world.instance_startup
    def explodes(ctx: Ctx) -> None:
        ctx.db.execute("INSERT INTO items (id, name) VALUES ('h3', 'third')")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        world.instance(None)
    assert list(world.work_dir.iterdir()) == []


def test_tools_never_lists_control(blank):
    assert [t["name"] for t in blank.tools()] == ["add_item", "tag_item", "finish_item"]
    assert blank.call("controller_digest")


def test_unknown_tool_raises(blank):
    with pytest.raises(UnknownTool, match="unknown tool: dance"):
        blank.call("dance")


def test_call_after_destroy_is_world_bug(toy_world):
    instance = toy_world.instance(None)
    instance.destroy()
    instance.destroy()
    with pytest.raises(WorldBug, match="is destroyed"):
        instance.call("add_item", name="x")
    with pytest.raises(WorldBug, match="is destroyed"):
        instance.inspect()


def test_destroy_waits_for_inflight_call(toy_world):
    started = threading.Event()
    release = threading.Event()

    @toy_world.tool
    def slow(ctx: Ctx) -> str:
        """Block until released."""
        started.set()
        release.wait(5)
        ctx.db.execute("INSERT INTO items (id, name) VALUES ('slow', 'slow')")
        return "done"

    instance = toy_world.instance(None)
    worker = threading.Thread(target=lambda: instance.call("slow"))
    worker.start()
    assert started.wait(5)
    destroyer = threading.Thread(target=instance.destroy)
    destroyer.start()
    time.sleep(0.05)
    assert not instance.closed
    release.set()
    worker.join(5)
    destroyer.join(5)
    assert instance.closed and not instance.dir.exists()


def test_control_call_under_lock_completes(toy_world):
    """The instance lock is re-entrant, so a control tool can open the read-only
    connection while the call that opened it holds the lock."""
    instance = toy_world.instance(None)
    try:
        instance.call("add_item", name="x")
        assert instance.call("controller_changes")
        assert instance.call("controller_digest") == instance.digest()
    finally:
        instance.destroy()


def test_inspect_sees_committed_not_uncommitted(blank):
    blank.call("add_item", name="committed")
    assert blank.inspect().one("SELECT count(*) AS n FROM items")["n"] == 1
    assert blank.inspect() is blank.inspect()
    with blank.db.transaction():
        blank.db.execute("INSERT INTO items (id, name) VALUES ('u', 'uncommitted')")
        assert blank.inspect().one("SELECT count(*) AS n FROM items")["n"] == 1
    assert blank.inspect().one("SELECT count(*) AS n FROM items")["n"] == 2


def test_bulk_commits_once_and_rolls_back_on_raise(blank):
    with blank.bulk() as ctx:
        assert ctx.call is None
        ctx.db.execute("INSERT INTO items (id, name) VALUES ('b1', 'one')")
        ctx.db.execute("INSERT INTO items (id, name) VALUES ('b2', 'two')")
    assert blank.db.one("SELECT count(*) AS n FROM items")["n"] == 2
    assert len(blank.changes()) == 2

    with pytest.raises(RuntimeError):
        with blank.bulk() as ctx:
            ctx.db.execute("INSERT INTO items (id, name) VALUES ('b3', 'three')")
            raise RuntimeError("boom")
    assert blank.db.one("SELECT count(*) AS n FROM items")["n"] == 2


def test_context_manager_destroys(toy_world):
    with toy_world.instance(None) as instance:
        directory = instance.dir
        assert directory.is_dir()
    assert not directory.exists()


def concurrency_peak(world, gate: int | None) -> int:
    """Run one slow query on each of two instances at once; report the peak overlap
    observed inside the tool itself."""
    running: list[int] = []
    peak: list[int] = [0]
    lock = threading.Lock()

    @world.tool
    def slow_query(ctx: Ctx) -> int:
        """A CPU-bound query."""
        with lock:
            running.append(1)
            peak[0] = max(peak[0], len(running))
        try:
            return ctx.db.one(SLOW_SQL)["count(*)"]
        finally:
            with lock:
                running.pop()

    set_concurrency_gate(gate)
    made = [world.instance(None) for _ in range(2)]
    try:
        threads = [
            threading.Thread(target=instance.call, args=("slow_query",))
            for instance in made
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
    finally:
        set_concurrency_gate(None)
        for instance in made:
            instance.destroy()
    return peak[0]


def test_gate_serialises_with_concurrency_one(toy_world):
    assert concurrency_peak(toy_world, 1) == 1


def test_gate_zero_lets_calls_overlap(tmp_path):
    assert concurrency_peak(build_toy_world(tmp_path / "open"), 0) >= 2


def test_gate_zero_disables():
    set_concurrency_gate(0)
    try:
        assert instances_module._GATE is None
    finally:
        set_concurrency_gate(None)
    assert instances_module._GATE is not None
    with pytest.raises(WorldBug, match="negative"):
        set_concurrency_gate(-1)


def test_sweep_removes_dead_pid_keeps_live_and_configured_dir(tmp_path, monkeypatch):
    """A world with the default work directory clears out directories left by processes
    that are gone, and touches nothing else."""
    monkeypatch.setattr(
        instances_module.tempfile, "gettempdir", lambda: str(tmp_path / "tmp")
    )
    root = Path(tempfile.gettempdir()) / WORK_ROOT_NAME
    dead = root / "999999999" / "toy"
    live = root / str(os.getpid()) / "toy"
    not_a_pid = root / "notapid"
    for directory in (dead, live, not_a_pid):
        directory.mkdir(parents=True)

    configured = build_toy_world(tmp_path / "configured")
    with configured.instance(None):
        assert configured._manager.sweep_stale_processes() == 0
    assert dead.exists()

    default = build_toy_world(tmp_path / "default", work_dir=None)
    with default.instance(None):
        assert not dead.parent.exists()
        assert live.exists() and not_a_pid.exists()


def test_two_hundred_instances_one_fixture(toy_world, frozen):
    made = [toy_world.instance("base") for _ in range(200)]
    try:
        assert len({instance.id for instance in made}) == 200
        assert all(instance.dir.is_dir() for instance in made)
    finally:
        for instance in made:
            instance.destroy()
    assert list(toy_world.work_dir.iterdir()) == []


def test_determinism_same_fixture_seed_calls_equal_digest(toy_world, frozen):
    def run():
        instance = toy_world.instance("base", seed=3)
        try:
            instance.call("add_item", name="alpha")
            item = instance.call("add_item", name="beta")
            instance.call("tag_item", item_id=item["id"], tag="blue")
            instance.call("finish_item", item_id=item["id"])
            return instance.digest(), [c.to_dict() for c in instance.changes()]
        finally:
            instance.destroy()

    assert run() == run()


def test_isolation_25_instances_concurrent_writes_invisible_to_each_other(
    toy_world, frozen
):
    count = 25
    instances = [toy_world.instance("base", seed=index) for index in range(count)]
    results: dict[int, tuple[list[dict], str]] = {}
    barrier = threading.Barrier(count)

    def work(index: int) -> None:
        instance = instances[index]
        barrier.wait(30)
        for step in range(3):
            instance.call("add_item", name=f"worker-{index}-{step}")
        results[index] = (
            [c.to_dict() for c in instance.changes()],
            instance.digest(),
        )

    threads = [threading.Thread(target=work, args=(i,)) for i in range(count)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        assert len(results) == count
        for index, (changes, _) in results.items():
            names = sorted(change["after"]["name"] for change in changes)
            assert names == [f"worker-{index}-{step}" for step in range(3)]
    finally:
        for instance in instances:
            instance.destroy()

    same = [toy_world.instance("base", seed=1) for _ in range(2)]
    try:
        for instance in same:
            instance.call("add_item", name="identical")
        assert same[0].digest() == same[1].digest()
    finally:
        for instance in same:
            instance.destroy()


def test_instance_info_carries_derived_seed(toy_world, frozen):
    instance = toy_world.instance("base", seed=9)
    try:
        assert instance.ctx.instance.fixture == "base"
        assert instance.ctx.instance.id == instance.id
        assert instance.seed == instance.ctx.instance.seed
        assert len(instance.seed) == 32
    finally:
        instance.destroy()
