from __future__ import annotations

import logging
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path
from kiln_server.document_api import get_rag_config_from_id
from kiln_server.git_sync_decorators import no_write_lock
from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import agent_policy_require_approval
from pydantic import BaseModel, Field

from .jobs.registry import job_registry

logger = logging.getLogger(__name__)


class RunRagConfigResponse(BaseModel):
    """Response returned when a RAG config run is kicked off."""

    kiln_job_tracking_id: str = Field(
        description="Background job id spawned for this RAG run. Use it to "
        "follow live progress via the jobs events stream or to poll the job "
        "record."
    )


def connect_rag_jobs_api(app: FastAPI) -> None:
    @app.get(
        "/api/projects/{project_id}/rag_configs/{rag_config_id}/run",
        tags=["Documents"],
        openapi_extra=agent_policy_require_approval(
            "Run RAG config indexing? This re-indexes documents and may take time."
        ),
    )
    @no_write_lock
    async def run_rag_config(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        rag_config_id: Annotated[
            str, Path(description="The unique identifier of the RAG configuration.")
        ],
    ) -> RunRagConfigResponse:
        """Kick off a RAG ingestion as a tracked background job.

        Returns immediately with the job id; the worker streams progress via
        the jobs SSE bus (`GET /api/jobs/events`). Idempotent: re-running the
        same RAG config supersedes any in-flight predecessor (cancel + remove)
        instead of stacking a duplicate row in the jobs panel.
        """
        project = project_from_id(project_id)
        rag_config = get_rag_config_from_id(project, rag_config_id)
        if rag_config.is_archived:
            raise HTTPException(
                status_code=422,
                detail="This RAG configuration is archived. You must unarchive it to use it.",
            )

        job = await job_registry.create(
            "rag",
            {
                "project_id": project_id,
                "rag_config_id": rag_config_id,
            },
            project_id=project_id,
            metadata={
                "tag": {
                    "kind": "rag",
                    "rag_config_id": rag_config_id,
                },
                # Initial display lines. The worker rewrites `secondary` on
                # every tick with per-phase progress; this seed is what the
                # row shows before the first tick.
                "display": {
                    "primary": f"RAG: {rag_config.name}",
                    "secondary": ["Starting…"],
                },
            },
            # Lifecycle identity: one logical run per RAG config. Re-launching
            # the same config supersedes the in-flight predecessor — replaces
            # the legacy 1-hour `shared_async_lock_manager` lock with a clean
            # cancel+restart semantic visible in the panel.
            idempotency_key=f"rag:{rag_config_id}",
        )

        return RunRagConfigResponse(kiln_job_tracking_id=job.id)
