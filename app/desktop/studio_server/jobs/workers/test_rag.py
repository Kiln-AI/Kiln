from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kiln_ai.adapters.rag.progress import RagProgress

from app.desktop.studio_server.jobs.workers.rag import RagJobParams, RagJobWorker


class _NoopCtx:
    job_id = "j_test"
    run_id = "run_test"

    async def report_progress(self, success, error=0, total=None, message=None):
        pass

    async def report_error(self, error_message, **extra):
        pass

    async def report_display(self, primary=None, secondary=None):
        pass

    async def report_metadata_patch(self, patch):
        pass


def _fake_runner(progress: RagProgress) -> MagicMock:
    runner = MagicMock()

    async def _run():
        yield progress

    runner.run = _run
    return runner


@pytest.mark.asyncio
async def test_run_threads_save_context_into_rag_workflow_runner():
    """Regression: RAG ingestion writes must go through the project's git-sync
    save context, so background runs are committed/pushed for auto-sync
    projects instead of being left dirty (and stashed away on the next
    ensure_clean). The worker must pass save_context into the runner builder.
    """
    params = RagJobParams(project_id="p1", rag_config_id="rc1")
    sentinel = object()
    fake_project = MagicMock()
    fake_rag_config = MagicMock()

    with (
        patch(
            "app.desktop.studio_server.jobs.workers.rag._load_rag_config",
            return_value=(fake_rag_config, fake_project),
        ),
        patch(
            "app.desktop.studio_server.jobs.workers.rag.save_context_for_project",
            return_value=sentinel,
        ) as mock_save_ctx,
        patch(
            "app.desktop.studio_server.jobs.workers.rag.build_rag_workflow_runner",
            new=AsyncMock(return_value=_fake_runner(RagProgress())),
        ) as mock_build,
        patch(
            "app.desktop.studio_server.jobs.workers.rag.compute_current_progress_for_rag_config",
            new=AsyncMock(return_value=RagProgress()),
        ),
    ):
        await RagJobWorker().run(params, _NoopCtx())

    mock_save_ctx.assert_called_once_with("p1", context="rag job rc1")
    mock_build.assert_awaited_once_with(fake_project, "rc1", save_context=sentinel)
