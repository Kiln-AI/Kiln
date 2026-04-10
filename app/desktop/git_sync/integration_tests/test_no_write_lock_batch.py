"""Batch operation integration tests for @no_write_lock endpoints.

Scenario 44: Partial failure across iterations — earlier commits remain
pushed even if a later iteration fails. This is intentional by design.
"""

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop.git_sync.decorators import no_write_lock
from app.desktop.git_sync.integration_tests.conftest import (
    PROJECT_ID,
    assert_clean_working_tree,
    auto_config,
    mock_git_sync_config,
    remote_has_commit,
)
from app.desktop.git_sync.middleware import GitSyncMiddleware
from app.desktop.git_sync.registry import GitSyncRegistry


def _build_batch_app(
    local_path: Path,
    file_prefix: str,
    api_path: str,
    iteration_commits: list[str] | None = None,
) -> tuple[FastAPI, str]:
    """Build a FastAPI app with a @no_write_lock batch endpoint.

    The endpoint runs 3 iterations: the first two commit+push,
    the third rolls back and raises ValueError.

    Returns the app and the full endpoint path.
    """
    app = FastAPI()
    app.add_middleware(GitSyncMiddleware)  # type: ignore[invalid-argument-type]
    endpoint_url = f"/api/projects/{PROJECT_ID}/{api_path}"

    @app.post(endpoint_url)
    @no_write_lock
    async def batch_endpoint() -> dict[str, Any]:
        manager = GitSyncRegistry.get_or_create(
            repo_path=local_path, auth_mode="system_keys"
        )

        for i in range(3):
            async with manager.write_lock():
                await manager.ensure_clean()
                await manager.ensure_fresh()
                pre_head = await manager.get_head()

                (local_path / f"{file_prefix}_{i}.kiln").write_text(
                    f"{file_prefix} {i}"
                )

                if await manager.has_dirty_files():
                    if i == 2:
                        await manager.rollback(pre_head)
                        raise ValueError(f"Simulated failure on iteration {i}")
                    await manager.commit_and_push(
                        api_path=api_path,
                        pre_request_head=pre_head,
                    )
                    if iteration_commits is not None:
                        iteration_commits.append(await manager.get_head())

        return {"ok": True}

    @app.get(f"/api/projects/{PROJECT_ID}/test_read")
    def test_read() -> dict[str, str]:
        return {"status": "ok"}

    return app, endpoint_url


class TestNoWriteLockPartialFailure:
    """Scenario 44: Batch @no_write_lock — earlier iterations committed, later fails."""

    @pytest.mark.asyncio
    async def test_partial_failure_earlier_commits_survive(self, git_repos):
        """Commits from iterations 1 and 2 survive even when iteration 3 fails."""
        local_path, remote_path = git_repos
        config = auto_config(str(local_path))
        iteration_commits: list[str] = []

        app, endpoint_url = _build_batch_app(
            local_path, "batch", "batch_op", iteration_commits
        )

        with mock_git_sync_config(config):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(endpoint_url)

            assert resp.status_code == 500

            assert len(iteration_commits) == 2
            for commit_hex in iteration_commits:
                assert remote_has_commit(remote_path, commit_hex)

            assert (local_path / "batch_0.kiln").exists()
            assert (local_path / "batch_1.kiln").exists()

    @pytest.mark.asyncio
    async def test_partial_failure_iteration3_rolled_back(self, git_repos):
        """Iteration 3's changes are rolled back after failure."""
        local_path, remote_path = git_repos
        config = auto_config(str(local_path))

        app, endpoint_url = _build_batch_app(local_path, "batch2", "batch_op2")

        with mock_git_sync_config(config):
            client = TestClient(app, raise_server_exceptions=False)
            client.post(endpoint_url)

            assert not (local_path / "batch2_2.kiln").exists()
            assert_clean_working_tree(local_path)
