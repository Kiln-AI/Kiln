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

**You detect the need and set it up.** RAG setup involves multiple steps (upload docs, configure extraction, chunking, embedding, vector store). The app's Create Search Tool flow does them with recommended templates, so it is the default; deep-link it. When the user asks you to do it through the API, you can (below).

1. Recognize that the user's problem is a knowledge problem (not a prompt or model problem)
2. Explain RAG briefly and why it helps
3. Check the state: is the library set up, which documents and RAG configs exist ("Checking RAG State" below)
4. Set it up: in the app (deep links below), or through the API ("Setting up RAG through the API" below)
5. Attach the search tool to a run config via `tools_config` — a new run config, since run configs cannot be edited

### Kiln RAG constraints (do not contradict)

- **RAG config creation lives inside the Create Search Tool flow** — there is no standalone "Create RAG Config" UI; deep-link [Create Search Tool](http://localhost:8757/docs/rag_configs/{project_id}/add_search_tool) and let it orchestrate end-to-end.
- **The app has recommended templates.** Don't enumerate embedding, chunker, or reranker choices to the user — recommend the app flow; only one vector store is supported, so never present it as a choice.
- **Extraction applies to PDFs / Office / images — skipped for `.txt` / `.md` inputs.** Don't narrate an extractor step for plain-text uploads.
- **Tags scope indexing, not search.** A doc can be tagged at upload and a RAG config can be scoped to that tag; there is no query-time tag filter.
- **Run configs are immutable.** Workflow: edit the prompt → test on the [Run page](http://localhost:8757/run) → save a new run config (including the search tool) once it's working. Never say "edit your run config".

### Running / re-indexing a RAG config

`GET /api/projects/{project_id}/rag_configs/{rcid}/run` runs the ingestion (extract → chunk → embed → index) and **streams progress via SSE**. It runs extraction and embedding model calls over every document, so tell the user before you start it. When the stream ends, read the progress below to check the result. This is **not** a background job — there is no `rag` job type, no job id, and `POST /api/jobs/rag` would 404. For a one-off readiness/progress read without streaming, use `POST /api/projects/{project_id}/rag_configs/progress` (see `references/knowledge/api_docs/documents_api_list.md`). The runner skips already-processed docs, so re-running is safe.

### Setting up RAG through the API

Read `references/knowledge/api_docs/documents_api_list.md` and each endpoint doc first.

1. **Documents.** The user adds files in the app's document library (`http://localhost:8757/docs/library/{project_id}`): `call_kiln_api` sends JSON, not files. List them with `GET /api/projects/{project_id}/documents`.
2. **The four parts.** A RAG config needs an extractor, a chunker, an embedding and a vector store config. Reuse existing ones (`GET .../extractor_configs`, `.../chunker_configs`, `.../embedding_configs`, `.../vector_store_configs`) or create them (`POST .../create_extractor_config` and the matching endpoints).
3. **The RAG config** — `POST /api/projects/{project_id}/rag_configs/create_rag_config` with the four IDs, optional `tags` to scope it, and the `tool_name` and `tool_description` that the agent reads (see `references/knowledge/tools.md`, "Tool name & description guidance").
4. **Index** with the run above, then check the progress.
5. **Search it** with `POST .../rag_configs/{rag_config_id}/search` on a question the user expects, before you attach it.

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

## See also

When and why, in the knowledge: `references/improving_agents/playbooks/answers-not-grounded.md`, `references/improving_agents/techniques/attach-the-knowledge-source.md`, `references/improving_agents/techniques/answer-only-from-the-source.md`, `references/improving_agents/techniques/document-into-a-skill.md`, `references/improving_agents/smells/document-behind-a-lookup-tool.md`.
