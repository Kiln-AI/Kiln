"""One private copy of a fixture, for one episode.

An instance is a directory holding a writable copy of a fixture's `state.sqlite`, a clock
frozen at that fixture's timestamp, and a seeded id source. Sessions never share one: the
eval runner drives twenty-five at once and each has to be able to write freely without any
of the others noticing.

Two locks, at different scales. Each instance has an `RLock` so its own calls are ordered
(and re-entrant, so a control tool that opens the read-only connection under the lock does
not deadlock). The process has one bounded semaphore so CPU-heavy calls across instances do
not oversubscribe the machine; it is taken *before* the instance lock, so a queued call
holds nothing and never delays a destroy.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import threading
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ContextManager, Iterator, Mapping

from . import changes as changes_module
from . import control
from . import fixtures as fixtures_module
from .call import Call
from .clock import Clock
from .ctx import Ctx, InstanceInfo
from .db import Db, build_blank, open_inspection, open_instance
from .errors import UnknownTool, WorldBug
from .fixtures import STATE_NAME, Fixture
from .ids import Ids, instance_seed

if TYPE_CHECKING:
    from .world import World

BASELINE_NAME = "baseline.sqlite"
WORK_ROOT_NAME = "kiln_worlds"

_GATE_LOCK = threading.Lock()


def _default_gate_size() -> int:
    count = getattr(os, "process_cpu_count", None)
    cpus = count() if count is not None else os.cpu_count()
    return min(cpus or 4, 16)


_GATE: threading.BoundedSemaphore | None = threading.BoundedSemaphore(
    _default_gate_size()
)


def set_concurrency_gate(n: int | None) -> None:
    """Resize the process-wide call gate. `None` restores the default, `0` disables it."""
    global _GATE
    if n is not None and n < 0:
        raise WorldBug(f"concurrency gate must not be negative, got {n}")
    with _GATE_LOCK:
        if n is None:
            _GATE = threading.BoundedSemaphore(_default_gate_size())
        elif n == 0:
            _GATE = None
        else:
            _GATE = threading.BoundedSemaphore(n)


def _gate() -> ContextManager[Any]:
    gate = _GATE
    return nullcontext() if gate is None else gate


class Instance:
    def __init__(
        self,
        manager: "InstanceManager",
        world: "World",
        instance_id: str,
        fixture: str | None,
        directory: Path,
        db: Db,
        ctx: Ctx,
        baseline_path: Path,
    ) -> None:
        self._manager = manager
        self._world = world
        self._db = db
        self._ctx = ctx
        self._baseline_path = baseline_path
        self._inspection: Db | None = None
        self._lock = threading.RLock()
        self.id = instance_id
        self.fixture = fixture
        self.seed = ctx.instance.seed
        self.clock = ctx.clock
        self.dir = directory
        self.closed = False

    @property
    def world(self) -> "World":
        return self._world

    @property
    def db(self) -> Db:
        return self._db

    @property
    def ctx(self) -> Ctx:
        return self._ctx

    def call(self, name: str, /, **arguments: Any) -> Any:
        tool = self._world.tools.get(name)
        if tool is None:
            raise UnknownTool(name)
        with nullcontext() if tool.control else _gate():
            with self._lock:
                if self.closed:
                    raise WorldBug(f"instance {self.id} is destroyed")
                call = Call(name, arguments, tool)
                ctx = self._ctx.with_call(call)
                if tool.control:
                    return control.dispatch(self, ctx)
                return self._world.chain(ctx, call)

    def tools(self) -> list[dict[str, Any]]:
        return [t.listing() for t in self._world.tools.values() if not t.control]

    def inspect(self) -> Db:
        """A read-only connection with the instance as `main` and its baseline as `base`."""
        with self._lock:
            if self.closed:
                raise WorldBug(f"instance {self.id} is destroyed")
            if self._inspection is None:
                self._inspection = open_inspection(
                    self.dir / STATE_NAME,
                    self.clock,
                    attach={"base": self._baseline_path},
                )
            return self._inspection

    def changes(self) -> list[changes_module.Change]:
        with self._lock:
            return changes_module.diff(self.inspect(), self._world.tracked_tables)

    def digest(self) -> str:
        with self._lock:
            return changes_module.digest(
                self.inspect(), self._world.tracked_tables, self._world.schema_hash
            )

    def freeze(self, id: str, description: str) -> Fixture:
        with self._lock:
            return fixtures_module.freeze(
                self, id, description, fixtures_dir=self._world.fixtures_dir
            )

    @contextmanager
    def bulk(self) -> Iterator[Ctx]:
        """One transaction for a whole load. Writes made here are agent-visible changes."""
        with self._lock:
            if self.closed:
                raise WorldBug(f"instance {self.id} is destroyed")
            with self._db.transaction():
                yield self._ctx

    def destroy(self) -> None:
        self._manager.destroy(self)

    def __enter__(self) -> "Instance":
        return self

    def __exit__(self, *exc: object) -> None:
        self.destroy()


class InstanceManager:
    """Every live instance of one world, and the work directory they live in."""

    def __init__(self, world: "World") -> None:
        self._world = world
        self._lock = threading.Lock()
        self._instances: dict[str, Instance] = {}
        self._work_dir: Path | None = None
        self._configured_work_dir = world.work_dir is not None

    # ---- work directory ----

    def _work_root(self) -> Path:
        """The directory instances live in, resolved once.

        Under the lock: two threads creating the first two instances must not both sweep and
        both register an atexit hook.
        """
        with self._lock:
            if self._work_dir is None:
                configured = self._world.work_dir
                self._work_dir = (
                    Path(configured)
                    if configured is not None
                    else Path(tempfile.gettempdir())
                    / WORK_ROOT_NAME
                    / str(os.getpid())
                    / self._world.name
                )
                atexit.register(self.close)
                if not self._configured_work_dir:
                    self.sweep_stale_processes()
            return self._work_dir

    def sweep_stale_processes(self) -> int:
        """Remove work directories left by processes that are gone. A caller-supplied work
        directory is never swept: it may be shared on purpose."""
        if self._configured_work_dir:
            return 0
        root = Path(tempfile.gettempdir()) / WORK_ROOT_NAME
        if not root.is_dir():
            return 0
        removed = 0
        for child in root.iterdir():
            if not child.is_dir() or not child.name.isdigit():
                continue
            pid = int(child.name)
            if pid == os.getpid() or _process_alive(pid):
                continue
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
        return removed

    # ---- lifecycle ----

    def create(
        self,
        fixture_id: str | None,
        *,
        seed: int | bytes | None = None,
        now: str | datetime | None = None,
        startup_kwargs: Mapping[str, Any] = {},
    ) -> Instance:
        accepted_by_any_hook = self._world.accepted_startup_kwargs
        if accepted_by_any_hook is not None:
            unknown = sorted(set(startup_kwargs) - accepted_by_any_hook)
            if unknown:
                raise WorldBug(f"unknown reset argument(s): {unknown}")
        if fixture_id is not None and now is not None:
            raise WorldBug(
                "now= applies to blank instances only; a fixture carries its own timestamp"
            )

        fixture: Fixture | None = None
        if fixture_id is not None:
            fixture = self._world.fixture(fixture_id)
            fixtures_module.verify(fixture)
            if fixture.meta.schema_hash != self._world.schema_hash:
                raise WorldBug(
                    f"fixture {fixture_id!r} was frozen from a different schema; "
                    "regenerate it"
                )

        instance_id = str(uuid.uuid4())
        directory = self._work_root() / instance_id
        directory.mkdir(parents=True)

        db: Db | None = None
        try:
            state = directory / STATE_NAME
            if fixture is None:
                build_blank(state, self._world.schema).close()
                clock = _blank_clock(now)
                seed_source = self._world.name
            else:
                shutil.copyfile(fixture.state_path, state)
                os.chmod(state, 0o644)
                clock = Clock.from_iso(fixture.now)
                seed_source = fixture.id

            derived = instance_seed(seed_source, seed)
            db = open_instance(state, clock)
            ctx = Ctx(
                db=db,
                clock=clock,
                ids=Ids(derived),
                state={},
                instance=InstanceInfo(instance_id, fixture_id, derived),
            )

            hooks = self._world.startup_hooks
            if hooks:
                with db.transaction():
                    for hook, accepted_by_hook in zip(
                        hooks, self._world.startup_hook_kwargs
                    ):
                        hook(ctx, **_kwargs_for(accepted_by_hook, startup_kwargs))

            if fixture is not None and not hooks:
                baseline_path = fixture.state_path
            else:
                baseline_path = directory / BASELINE_NAME
                db.conn.execute("VACUUM INTO ?", (str(baseline_path),))
                os.chmod(baseline_path, 0o444)

            instance = Instance(
                self,
                self._world,
                instance_id,
                fixture_id,
                directory,
                db,
                ctx,
                baseline_path,
            )
        except BaseException:
            if db is not None:
                db.close()
            shutil.rmtree(directory, ignore_errors=True)
            raise

        with self._lock:
            self._instances[instance_id] = instance
        return instance

    def destroy(self, instance: Instance) -> None:
        with self._lock:
            self._instances.pop(instance.id, None)
        with instance._lock:
            if instance.closed:
                return
            instance.closed = True
            if instance._inspection is not None:
                instance._inspection.close()
                instance._inspection = None
            instance._db.close()
            shutil.rmtree(instance.dir, ignore_errors=True)

    def close(self) -> None:
        with self._lock:
            live = list(self._instances.values())
        for instance in live:
            try:
                self.destroy(instance)
            except Exception:
                pass


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _blank_clock(now: str | datetime | None) -> Clock:
    if now is None:
        return Clock.wall()
    if isinstance(now, str):
        return Clock.from_iso(now)
    return Clock(now)


def _kwargs_for(
    accepted_by_hook: frozenset[str] | None, startup_kwargs: Mapping[str, Any]
) -> dict[str, Any]:
    """A hook taking **kwargs gets everything; one with named keyword arguments gets the
    subset it declares, so two hooks can accept different reset arguments."""
    if accepted_by_hook is None:
        return dict(startup_kwargs)
    return {k: v for k, v in startup_kwargs.items() if k in accepted_by_hook}
