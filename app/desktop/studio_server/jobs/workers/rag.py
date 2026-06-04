from __future__ import annotations

from kiln_ai.adapters.rag.progress import (
    RagProgress,
    compute_current_progress_for_rag_config,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from kiln_server.document_api import build_rag_workflow_runner
from kiln_server.project_api import project_from_id
from pydantic import BaseModel

from ..models import JobContext, JobDerivedState, JobWorker


class RagJobParams(BaseModel):
    project_id: str
    rag_config_id: str


class RagJobResult(BaseModel):
    documents_total: int
    documents_completed: int
    chunks_indexed: int
    errors: int


def _rag_step_lines(progress: RagProgress) -> list[str]:
    """Render the four-phase progress as a list of one-liners for the jobs
    table's Details column. Lines mirror what the legacy run_rag_dialog showed
    via per-phase progress bars, condensed for the table view.
    """
    total_docs = progress.total_document_count
    return [
        _line(
            "Extracted",
            progress.total_document_extracted_count,
            total_docs,
            progress.total_document_extracted_error_count,
        ),
        _line(
            "Chunked",
            progress.total_document_chunked_count,
            total_docs,
            progress.total_document_chunked_error_count,
        ),
        _line(
            "Embedded",
            progress.total_document_embedded_count,
            total_docs,
            progress.total_document_embedded_error_count,
        ),
        _line(
            "Indexed",
            progress.total_chunks_indexed_count,
            progress.total_chunk_count,
            progress.total_chunks_indexed_error_count,
            unit="chunks",
        ),
    ]


def _line(label: str, done: int, total: int, errors: int, unit: str = "docs") -> str:
    base = f"{label}: {done} / {total} {unit}" if total else f"{label}: {done} {unit}"
    return f"{base} · {errors} errored" if errors else base


def _aggregate_errors(progress: RagProgress) -> int:
    return (
        progress.total_document_extracted_error_count
        + progress.total_document_chunked_error_count
        + progress.total_document_embedded_error_count
        + progress.total_chunks_indexed_error_count
    )


def _load_rag_config(params: RagJobParams) -> tuple[RagConfig, Project]:
    """Resolve the on-disk RagConfig + parent project. Raised errors land in
    the job's `failed` state — the same outcome the user would have gotten
    from the inline endpoint.
    """
    project = project_from_id(params.project_id)
    rag_config = RagConfig.from_id_and_parent_path(params.rag_config_id, project.path)
    if rag_config is None:
        raise ValueError(f"RAG config {params.rag_config_id} not found")
    return rag_config, project


class RagJobWorker(JobWorker[RagJobParams, RagJobResult]):
    """Background worker that runs a RAG ingestion workflow against one config.

    Wraps the existing `RagWorkflowRunner` unchanged. Multi-phase progress is
    surfaced two ways:
    - `report_progress` carries the headline (documents-completed / total +
      aggregate error count) so the generic Progress column / bar work.
    - `report_display` rewrites `metadata.display.secondary` to a per-phase
      list every tick — that's what gives the row its richer "Extracted X/Y ·
      Chunked X/Y · ..." breakdown the user sees in the Details column.

    Idempotent: each step's `collect_jobs` skips items whose downstream
    artifact (Extraction / ChunkedDocument / ChunkEmbeddings) already exists
    for the matching config_id, so pause-then-resume picks up where it left
    off without re-running completed items.
    """

    type_name = "rag"
    params_model = RagJobParams
    result_model = RagJobResult
    supports_pause = True

    async def compute_state(self, params: RagJobParams) -> JobDerivedState:
        rag_config, project = _load_rag_config(params)
        progress = await compute_current_progress_for_rag_config(project, rag_config)
        total = progress.total_document_count
        success = progress.total_document_completed_count
        # is_complete only when all docs are processed AND all chunks indexed
        # (indexing can lag chunking if a prior run died mid-indexing).
        chunks_complete = (
            progress.total_chunk_count > 0
            and progress.total_chunks_indexed_count >= progress.total_chunk_count
        ) or (
            # No chunks at all (e.g. empty dataset) — chunks aren't the gating
            # signal; document completion is what matters.
            progress.total_chunk_count == 0
        )
        return JobDerivedState(
            total=total,
            success=success,
            # error left None: per-phase error counts only exist at runtime —
            # source-of-truth entities don't persist failures. The registry
            # preserves the live count last reported via report_progress,
            # keeping View Errors meaningful across a pause.
            is_complete=total > 0 and success >= total and chunks_complete,
            message=None,
        )

    async def run(self, params: RagJobParams, ctx: JobContext) -> RagJobResult:
        rag_config, project = _load_rag_config(params)
        runner = await build_rag_workflow_runner(project, params.rag_config_id)

        # Track how many log entries we've already forwarded to the per-run
        # error log so we don't re-report the same error on every subsequent
        # tick. `progress.logs` is the cumulative list — we just need a
        # high-water-mark index.
        forwarded_log_count = 0

        latest: RagProgress | None = None
        async for progress in runner.run():
            latest = progress

            # Forward any newly-arrived error-level logs to the per-run error
            # log so they show up under "View Errors" in the jobs panel. The
            # runner now accumulates logs on RagProgress.logs, so we slice
            # from where we left off.
            for log in (progress.logs or [])[forwarded_log_count:]:
                if log.level == "error":
                    await ctx.report_error(log.message)
            forwarded_log_count = len(progress.logs or [])

            errors = _aggregate_errors(progress)
            await ctx.report_progress(
                success=progress.total_document_completed_count,
                error=errors,
                total=progress.total_document_count,
            )
            await ctx.report_display(secondary=_rag_step_lines(progress))
            # Stamp the full RagProgress snapshot so the existing four-bar
            # frontend dialog can keep showing per-phase percentages.
            await ctx.report_metadata_patch(
                {"rag_progress": progress.model_dump(mode="json")}
            )

        if latest is None:
            # RagWorkflowRunner always yields at least the initial_progress, so
            # this shouldn't be reachable — but if it ever is, return zeros
            # rather than letting the result_model validation fail.
            return RagJobResult(
                documents_total=0,
                documents_completed=0,
                chunks_indexed=0,
                errors=0,
            )

        # Re-snapshot from on-disk reality for the final reported counts.
        # During the run, the workflow tracks per-phase counts as
        # baseline + step_success_count, but a sibling RAG run that shares one
        # of our step configs (extractor / chunker / embedder) can complete
        # work between our step's collect_jobs and the end of our run, leaving
        # our tracked counters behind disk reality. The disk snapshot doesn't
        # know about runtime errors (those entities aren't persisted), so we
        # carry the workflow's per-phase error counts and accumulated logs
        # over from `latest`.
        disk_progress = await compute_current_progress_for_rag_config(
            project, rag_config
        )
        final_progress = disk_progress.model_copy(
            update={
                "total_document_extracted_error_count": latest.total_document_extracted_error_count,
                "total_document_chunked_error_count": latest.total_document_chunked_error_count,
                "total_document_embedded_error_count": latest.total_document_embedded_error_count,
                "total_chunks_indexed_error_count": latest.total_chunks_indexed_error_count,
                "logs": latest.logs,
            }
        )
        final_errors = _aggregate_errors(final_progress)
        await ctx.report_progress(
            success=final_progress.total_document_completed_count,
            error=final_errors,
            total=final_progress.total_document_count,
        )
        await ctx.report_display(secondary=_rag_step_lines(final_progress))
        await ctx.report_metadata_patch(
            {"rag_progress": final_progress.model_dump(mode="json")}
        )

        return RagJobResult(
            documents_total=final_progress.total_document_count,
            documents_completed=final_progress.total_document_completed_count,
            chunks_indexed=final_progress.total_chunks_indexed_count,
            errors=final_errors,
        )
