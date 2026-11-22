---
name: rag
description: |
  RAG setup: document library, search tool configuration, and troubleshooting. Load when: the agent needs domain knowledge, user mentions docs/PDFs, 'it doesn't know about our X', or hallucinates company-specific info.
---
# Knowledge: RAG (Retrieval-Augmented Generation)

RAG lets agents search your uploaded documents before answering — grounding responses in your actual data instead of hallucinating. In Kiln: upload docs → extraction + embedding → create a RAG search tool → agent searches the doc store at inference time.

## Common mistakes to avoid (read before answering RAG questions)

- **Tags scope *indexing*, not *search*.** A doc can be tagged at upload and a RAG config can be scoped to a tag at configuration time; there is **no query-time tag filter**. If a user asks "can I filter my search by tag?" the answer is: tags decide which docs were indexed into a RAG config, not which docs are retrieved at query time.
- **Extraction is per-format, and it's skipped for plain text.** `.pdf`, `.docx`, `.png` and similar → the extractor runs. `.txt`, `.md` → the extractor is skipped; the text is already plain. Don't narrate an extractor step for plain-text uploads.

## API Docs

Load the relevant endpoint doc **before** making each API call — they have request body schemas, response fields, and parameter details. Use the Documents catalog for the full RAG/documents index; use the companion catalogs for embedding or reranker model discovery and for enabling the RAG search tool on a task (`tools_config`).

| Resource | Load |
|----------|------|
| **Documents & RAG (catalog)** | `references/knowledge/api_docs/documents_api_list.md` |
| Run configs (catalog) | `references/knowledge/api_docs/run_configs_api_list.md` |
| Tools & MCP (catalog) | `references/knowledge/api_docs/tools_mcp_api_list.md` |
| Providers & models (catalog) | `references/knowledge/api_docs/providers_models_api_list.md` |
| GET check library state | `references/knowledge/api_docs/get_api_projects_project_id_check_library_state.md` |
| GET list documents | `references/knowledge/api_docs/get_api_projects_project_id_documents.md` |
| GET list RAG configs | `references/knowledge/api_docs/get_api_projects_project_id_rag_configs.md` |

## The Agent's Role with RAG

**You detect the need and link to the UI.** RAG setup involves multiple complex steps (upload docs, configure extraction, chunking, embedding, vector store) that the Kiln UI handles with a guided workflow.

1. Recognize that the user's problem is a knowledge problem (not a prompt or model problem)
2. Explain RAG briefly and why it helps
3. Deep-link to the document library and RAG setup
4. After setup, remind the user to enable the RAG tool in their run config via `tools_config`

### Kiln RAG constraints (do not contradict)

- **RAG config creation lives inside the Create Search Tool flow** — there is no standalone "Create RAG Config" UI; deep-link [Create Search Tool](`http://localhost:8757/docs/rag_configs/{project_id}/add_search_tool`) and let it orchestrate end-to-end.
- **The UI has recommended templates.** Don't enumerate embedding, chunker, or reranker choices — hand off; only one vector store is supported, so never present it as a choice.
- **Extraction applies to PDFs / Office / images — skipped for `.txt` / `.md` inputs.** Don't narrate an extractor step for plain-text uploads.
- **Tags scope indexing, not search.** A doc can be tagged at upload and a RAG config can be scoped to that tag; there is no query-time tag filter.
- **Run configs are immutable.** Workflow: edit the prompt → test in [/run](`http://localhost:8757/run`) → save a new run config (including the search tool) once it's working. Never say "edit your run config".

### Running / re-indexing a RAG config

If you do trigger indexing via the API, `GET /api/projects/{project_id}/rag_configs/{rcid}/run` runs the ingestion (extract → chunk → embed → index) and **streams progress via SSE**. It requires user approval. This is **not** a background job — there is no `rag` job type, no job id, and `POST /api/jobs/rag` would 404. For a one-off readiness/progress read without streaming, use `POST /api/projects/{project_id}/rag_configs/progress` (see `references/knowledge/api_docs/documents_api_list.md`). The runner skips already-processed docs, so re-running is safe.

## UI Deep Links

| Action | Link |
|--------|------|
| Document library | `http://localhost:8757/docs/{project_id}` |
| Create RAG search tool | `http://localhost:8757/docs/rag_configs/{project_id}/add_search_tool` |
| Manage RAG configs | `http://localhost:8757/docs/rag_configs/{project_id}` |

## Checking RAG State

- Read `references/knowledge/api_docs/get_api_projects_project_id_check_library_state.md`, then:
- `call_kiln_api("GET", "/api/projects/{project_id}/check_library_state")` — Is the library set up?
- Read `references/knowledge/api_docs/get_api_projects_project_id_documents.md`, then:
- `call_kiln_api("GET", "/api/projects/{project_id}/documents")` — List uploaded documents
- Read `references/knowledge/api_docs/get_api_projects_project_id_rag_configs.md`, then:
- `call_kiln_api("GET", "/api/projects/{project_id}/rag_configs")` — List RAG configs
