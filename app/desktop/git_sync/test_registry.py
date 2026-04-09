import threading

from app.desktop.git_sync.git_sync_manager import GitSyncManager
from app.desktop.git_sync.registry import GitSyncRegistry


def test_get_or_create_new(git_repos):
    local_path, _ = git_repos
    manager = GitSyncRegistry.get_or_create(local_path)
    assert isinstance(manager, GitSyncManager)


def test_get_or_create_returns_existing(git_repos):
    local_path, _ = git_repos
    m1 = GitSyncRegistry.get_or_create(local_path)
    m2 = GitSyncRegistry.get_or_create(local_path)
    assert m1 is m2


def test_get_manager_returns_none_for_unknown(tmp_path):
    assert GitSyncRegistry.get_manager(tmp_path / "nonexistent") is None


def test_register_and_get(git_repos):
    local_path, _ = git_repos
    manager = GitSyncManager(repo_path=local_path)
    GitSyncRegistry.register(local_path, manager)
    assert GitSyncRegistry.get_manager(local_path) is manager


def test_reset_clears_all(git_repos):
    local_path, _ = git_repos
    GitSyncRegistry.get_or_create(local_path)
    assert GitSyncRegistry.get_manager(local_path) is not None

    GitSyncRegistry.reset()
    assert GitSyncRegistry.get_manager(local_path) is None


def test_thread_safety(git_repos):
    local_path, _ = git_repos
    results: list[GitSyncManager] = []
    barrier = threading.Barrier(4)

    def create():
        barrier.wait()
        results.append(GitSyncRegistry.get_or_create(local_path))

    threads = [threading.Thread(target=create) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 4
    assert all(r is results[0] for r in results)
