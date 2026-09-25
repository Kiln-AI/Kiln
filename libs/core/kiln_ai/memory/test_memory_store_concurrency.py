"""Multi-process concurrency tests for the memory store.

The store is concurrent-append safe by design: each save writes a distinct
{id}/memory.kiln file, so N processes appending never collide. Writes are atomic
(temp file + os.replace, see Memory.save_to_file), so a reader in another process
never observes a torn file; same-record updates are last-writer-wins. These tests
spawn real OS processes (the Phase-0 topology is one process per session) against
a shared project folder.

Note: the model cache is per-process; each worker loads the project fresh, and
the assertions read from a fresh store so cross-process writes are seen on disk.
"""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from kiln_ai.datamodel import Project
from kiln_ai.memory import MemoryStore


def _save_worker(project_path: str, scope: str, count: int, prefix: str) -> list[str]:
    project = Project.load_from_file(Path(project_path))
    store = MemoryStore(project)
    ids: list[str] = []
    for i in range(count):
        memory = store.save_memory(overview=f"{prefix}-{i}", scope=scope, tags=[prefix])
        assert memory.id is not None
        ids.append(memory.id)
    return ids


def _update_worker(
    project_path: str, memory_id: str, value: str, iterations: int
) -> str:
    project = Project.load_from_file(Path(project_path))
    store = MemoryStore(project)
    for _ in range(iterations):
        store.update_memory(memory_id, overview=value)
    return value


def test_multiprocess_appends_all_survive(tmp_path: Path):
    project = Project(name="concurrent_append", path=tmp_path / "project.kiln")
    project.save_to_file()

    n_procs, per_proc = 4, 25
    with ProcessPoolExecutor(max_workers=n_procs) as executor:
        futures = [
            executor.submit(
                _save_worker, str(project.path), "project", per_proc, f"p{p}"
            )
            for p in range(n_procs)
        ]
        results = [f.result() for f in futures]

    all_ids = [i for result in results for i in result]
    expected = n_procs * per_proc
    # No lost appends, and every id is unique across processes.
    assert len(all_ids) == expected
    assert len(set(all_ids)) == expected

    # A fresh store sees every record on disk, and every record parses (no torn
    # reads even though the writes were concurrent).
    fresh = MemoryStore(Project.load_from_file(project.path))
    listed = fresh.list_memories(limit=expected + 10)
    assert listed.matched == expected
    assert len(fresh.get_memories(all_ids)) == expected


def test_multiprocess_same_id_update_last_writer_wins(tmp_path: Path):
    project = Project(name="concurrent_update", path=tmp_path / "project.kiln")
    project.save_to_file()
    store = MemoryStore(project)
    memory = store.save_memory(overview="initial", scope="project")
    assert memory.id is not None

    values = [f"writer-{k}" for k in range(4)]
    with ProcessPoolExecutor(max_workers=len(values)) as executor:
        futures = [
            executor.submit(_update_worker, str(project.path), memory.id, value, 15)
            for value in values
        ]
        [f.result() for f in futures]

    # Exactly one record, it loads cleanly (atomic writes: no torn read even under
    # concurrent same-file writes), and its value is one writer's — last-writer-wins,
    # no corrupt merge, no duplicate records.
    fresh = MemoryStore(Project.load_from_file(project.path))
    listed = fresh.list_memories()
    assert listed.matched == 1
    final = fresh.get_memories([memory.id])[0]
    assert final.overview in values
