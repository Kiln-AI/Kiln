---
status: complete
---

# Phase 4: Skills, the RAG chain, and the index-rebuild proof

## Overview

Phase 4 authors architecture.md's content group 5 — skills, then the RAG chain — and
closes the project out: a final pass on `.agents/USING_PLAYWRIGHT.md` describing what the
finished fixture holds, and a re-run of matrix cases 1–4 against it.

It also carries a **correction to architecture.md** given by the user during phase 3, and
step 1 below is to write that correction into architecture.md before any authoring starts.
The correction changes what group 5 must produce: not five configs, but five configs *plus
the outputs of running the chain* — the extractions and the embeddings — so that a seeded
sandbox with no API key can rebuild the index from committed data. Only the LanceDB index
itself stays out of the repo. The same split is what Kiln's git sync does: extracted docs
and embeddings sync, the index is a locally-cached derived artifact.

Nothing in this phase is application code. The diff should be JSON, markdown and
attachments under `.agents/playwright_project/`, plus the two spec/docs files and this
plan. Everything is created by clicking through the app at `http://localhost:6544` and
captured with `.agents/scripts/playwright_server.sh snapshot`.

### Ground truth read out of the code before planning

Every step below depends on one of these, so they were read first and are re-verified
against disk during the phase.

| Fact | Where it comes from |
|---|---|
| Documents, extractions, chunked documents and embeddings all nest **inside** the project directory | `Project(parent_of={"documents": Document, ...})` in `libs/core/kiln_ai/datamodel/project.py`; `Document(parent_of={"extractions": Extraction})`, `Extraction(parent_of={"chunked_documents": ChunkedDocument})`, `ChunkedDocument(parent_of={"chunk_embeddings": ChunkEmbeddings})` |
| The LanceDB index lives **outside** it | `LanceDBAdapter.lancedb_path_for_config` → `<data_dir>/rag_indexes/lancedb/<rag_config_id>` |
| The indexing step needs no provider | `RagIndexingStepRunner.collect_records` in `libs/core/kiln_ai/adapters/rag/rag_runners.py` walks documents → extractions → chunked documents → chunk embeddings on disk and inserts them; nothing in it calls a model |
| A `lancedb_hybrid` or `lancedb_vector` **search** does need one | `RagTool.search` in `libs/core/kiln_ai/tools/rag_tools.py` embeds the query for those two store types and not for `lancedb_fts` |
| Markdown and plaintext documents are never sent to the extraction model | `create_extractor_form.svelte` posts `passthrough_mimetypes: ["text/plain", "text/markdown"]` with no control over it, and `BaseExtractor._should_passthrough` short-circuits on that list |

The first three together are the whole reason the correction is right: extraction and
embedding outputs are capturable and the index is not, and the index can be rebuilt from
them offline.

## Steps

Each numbered group ends in a `snapshot` and a `git diff` review, per architecture.md's
resumability rule.

### 1. Write the correction into architecture.md

In the "Fixture authoring" section:

- Restate content group 5 as configs **plus** the extraction and embedding outputs.
- Add a subsection recording where each artifact lands relative to the project directory,
  which of them `snapshot` captures, and the resulting obligation: run extraction and
  embedding so their outputs are committed, then prove the rebuild from those outputs.
- Rewrite the "index must be shown to rebuild" risk so it is a statement about a rebuild
  from committed extractions and embeddings, not from configs alone.

This goes first because a future agent reads architecture.md and never this prompt.

### 2. Connect OpenRouter through the UI

Settings → Providers → OpenRouter → paste key → Connect. The sandbox carried over from
phase 3 has no providers — its `settings.yaml` holds only `projects`, `user_type` and
`personal_use_contact` — so the key is pasted again. Nothing here reaches the fixture;
`snapshot` never reads `settings.yaml`.

### 3. Two skills

Skills → Add Skill, twice. Each is three fields — kebab-case name, description,
instructions — and the instructions become the `SKILL.md` body beside `skill.kiln`
(`Skill.save_skill_md`). Two rather than one so the skills list screen has more than a
single row, and both are written for the project's support-triage subject so the fixture
reads as one coherent project.

Snapshot and commit.

### 4. The documents

Docs & Search → Library → Add Documents, uploading small markdown files written for this
project (routing playbook, escalation policy, an SLA/plan matrix). Markdown because
architecture.md asks for documents that stay small and textual, and because committed
embeddings scale with document length: three short documents keep the vectors to a size
worth putting in a repo.

Consequence to record rather than work around: with `passthrough_mimetypes` fixed at
`["text/plain", "text/markdown"]` by the UI, extraction of these documents is a
passthrough copy and the extractor's model is never invoked. The extractor config still
has to name a model, and the dropdown filters to `supports_doc_extraction`, which
`deepseek/deepseek-v4-flash-0731` is not — so the named model is one of the offered ones
and is unexercised by this fixture. That is a deviation worth stating plainly, not hiding
behind a model that looks used.

Snapshot and commit.

### 5. The chain, and running it

Docs & Search → Search Tools → Add Search Tool → **Custom**, since every built-in template
targets `gemini_api` or `ollama` and this sandbox has only OpenRouter. The create form's
five dropdowns each offer "create new", which opens the sub-config dialog inline, so the
whole chain is authored from one screen:

- **Extractor** — a model from the doc-extraction list, markdown output.
- **Chunker** — fixed window, the default 512/64.
- **Embedding** — OpenRouter, `openai/text-embedding-3-small`. 1536 dimensions is the
  smallest of the OpenRouter-served models measured to work, and each vector is committed
  as JSON, so dimensions are a repo-size decision as well as a quality one.
- **Vector store** — `lancedb_hybrid`, the app's own recommended default. Hybrid also
  means the committed embeddings are used at *query* time and not only at index time,
  which `lancedb_fts` would not do.
- **RAG config** — tool name and description, over all documents.

Then **Run** it from the search tool's page. That executes all four steps —
extraction, chunking, embedding, indexing — three of which write into the project
directory.

Snapshot and commit. The diff is the check that the correction is real: it must contain
`documents/*/extractions/*/extraction.kiln`, its output attachment, the chunked document
with a content attachment per chunk, and `chunk_embeddings/*/chunk_embeddings.kiln`
holding the vectors — and must contain no LanceDB file.

### 6. Prove the index rebuilds from a seeded sandbox

The proof has to start from a sandbox that has never seen the key, so this is the point in
the phase where `reset` is deliberate rather than costly:

1. Confirm the index is where the code says it is and that `snapshot` did not capture it.
2. `reset`. The sandbox is re-seeded from the committed fixture and its `settings.yaml` is
   the four lines `write_seed_settings` writes — no provider.
3. Land in the app, open the search tool, confirm it reports the documents as extracted,
   chunked and embedded but **not indexed**, from committed data alone.
4. **Run** it with no provider connected, and confirm the index builds.
5. Then connect OpenRouter and run a search from the tool's Search panel, so "indexes *and*
   queries" is shown rather than assumed. The query embedding is the one live call, and it
   is a property of `lancedb_hybrid`, not of the rebuild.

If step 4 fails, that is the roadblock the phase exists to find, and it gets reported
rather than papered over with a re-run that has the key connected.

### 7. Final docs pass and the matrix

- `.agents/USING_PLAYWRIGHT.md`: bring "The seeded project" up to date with everything the
  fixture now holds — the eval from phase 3, the skills, and the RAG chain — and say what
  a keyless sandbox can and cannot do with it.
- Re-run matrix cases 1–4 from phase 1 against the finished fixture and record the results
  in this plan.
- `grep -r` the working tree for the key body.
- Stop the server, then `uv run ./checks.sh --agent-mode` — its vite and backend starve
  `app/web_ui/src/lib/stores/jobs_store.test.ts` past its 5 s timeout if left running.

## Tests

No automated tests, and this is a decision rather than an omission: architecture.md's
"Testing strategy" rejects a pytest that loads the fixture, because `verify_seed_loaded`
catches the same rot at the moment an agent would be confused by it, without a test whose
failure mode is a red CI on an unrelated PR. Verification for this phase is:

- After each group, `snapshot` leaves a diff containing only files under
  `.agents/playwright_project/`, reviewed before moving on.
- The group-5 diff contains extractions, chunks and embeddings, and contains no LanceDB
  file. Checked by listing the diff, and by locating the index on disk and confirming it is
  outside the project directory.
- The index rebuild in step 6 runs against a `reset` sandbox with no provider connected —
  the settings file is read back to confirm that before the run, so "no key was used" is a
  measurement and not an assumption.
- A search through the tool's own panel returns chunks from the seeded documents.
- Every fixture screen touched this phase renders after the `reset`: the skills list, both
  skill bodies, the document library, and the search tool's config and progress.
- No occurrence of the OpenRouter key anywhere in the working tree.
- `uv run ./checks.sh --agent-mode` with the sandbox server stopped.

## What was authored

All ids are the real ones in the committed fixture.

### Skills

| Id | Name | What it says |
|---|---|---|
| `255490964102` | `ticket-routing-playbook` | Which team owns which kind of ticket, how priority is chosen, how to break a tie between two teams |
| `197586632641` | `escalation-and-reply-tone` | The four categories that force human review, that urgency alone is not one of them, and how a first reply should read |

Each is a `skill.kiln` plus a `SKILL.md` sidecar carrying the body, which is where
`Skill.save_skill_md` puts it. `save_skill_md` also creates empty `references/` and
`assets/` directories; git does not track empty directories, so they are not in the
fixture and nothing reads them.

### Documents

| Id | File | Words | Chunks |
|---|---|---|---|
| `256870847666` | `routing_playbook.md` | 650 | 2 |
| `149787447013` | `escalation_policy.md` | 528 | 2 |
| `888362551730` | `plan_tiers_and_slas.md` | 519 | 2 |

All three tagged `support_policy`, each with a description written on its detail page.

### The chain

| Model | Id | Notes |
|---|---|---|
| `ExtractorConfig` | `117940161350` | `Gemini 3p5 Flash Lite w Default Prompts`, `gemini_3_5_flash_lite` / `openrouter`, markdown output, `passthrough_mimetypes` `["text/plain", "text/markdown"]` |
| `ChunkerConfig` | `227908374129` | `Size 512 - Overlap 64`, fixed window |
| `EmbeddingConfig` | `289999549185` | `Text Embedding 3 Small (1536 dimensions)`, `openai_text_embedding_3_small` / `openrouter` |
| `VectorStoreConfig` | `934331727063` | `Hybrid Search - Vector and Full-Text`, `lancedb_hybrid`, top k 5 |
| `RagConfig` | `184180693413` | `Support Policy Search`, tool `support_policy_search`, no tag filter (all documents) |

Built through **Add Search Tool → Custom**, using each dropdown's "create new" dialog.
Custom rather than a built-in template because every template targets `gemini_api` or
`ollama` and this sandbox has only OpenRouter.

### What running the chain produced, and where it landed

Per document: an `extraction.kiln` with a markdown output attachment, a
`chunked_document.kiln` with a content attachment per chunk, and a
`chunk_embeddings.kiln` holding two 1536-dimension vectors. All three nest inside the
project directory and all three are committed — the three `chunk_embeddings.kiln`
files are 86952 + 86778 + 86700 = 260,430 bytes, so **254 KB of vectors** for six
chunks, or roughly 42 KB per 1536-dimension vector serialized as JSON floats. That is
the number to size a larger corpus against; the whole fixture is 1.3 MB.

The LanceDB index landed at
`app/web_ui/.agent_dev_home/.kiln_ai/rag_indexes/lancedb/184180693413`. Checked with
`os.path.realpath` against the project directory: not inside it, and the `snapshot`
diff contained no LanceDB file.

Every extraction has `source: passthrough`. The markdown corpus never reaches the
extraction model.

### The two risks, and how they came out

**OpenRouter embeddings work.** Established twice, and the second is the one that
counts: a raw `curl` to `https://openrouter.ai/api/v1/embeddings` with
`openai/text-embedding-3-small` returned 200 before any authoring started, and then
the app itself — going through Kiln's `openrouter/… → openai/…` slug rewrite and
LiteLLM — produced three `ChunkEmbeddings` records of two 1536-float vectors each. No
second key was needed. `openai/text-embedding-3-small` is the only OpenRouter
embedding model this phase exercised; the others in `ml_embedding_model_list.py`
remain unrun.

**The index rebuilds from committed data, with no provider.** The sequence, in order,
each step measured:

1. `reset`. `settings.yaml` came back as the four lines `write_seed_settings` writes —
   `projects`, `user_type`, `personal_use_contact`, and no `open_router_api_key`.
   `.kiln_ai/rag_indexes` did not exist.
2. The seeded sandbox's three `chunk_embeddings.kiln` files were present, from the
   fixture.
3. Docs & Search reported the search tool **Incomplete (95%)** — extraction 3/3,
   chunking 3/3, embedding 3/3, **indexing 0/6 chunks**. That state is reached from
   committed data alone.
4. **Run**, still with no key: indexing went to 6/6 and the tool read Complete. The
   index directory appeared, 96 KB.
5. A `snapshot` immediately after produced an **empty diff** — the rebuild writes
   nothing into the project directory.
6. OpenRouter was then connected and the tool's own Search panel queried
   *"When should a ticket be escalated to a human?"*: 5 results, the top two both
   chunks of `escalation_policy.md` (chunk #1 at 1.00, chunk #0 at 0.75). The query
   embedding is the one live call, and it is a property of `lancedb_hybrid` rather
   than of the rebuild.

### Matrix cases 1–4, re-run against the finished fixture

| # | Case | Result |
|---|---|---|
| 1 | Fresh home (`.agent_dev_home` deleted), `start` | Seeds. The printed three-command hint lands on `/run` showing "Task: Triage Ticket", not `/setup`. Skills, Document Library and Search Tools all render their fixture content |
| 2 | `start` again, already-running **and** after a `stop` | No re-seed — the stamp's `seeded_at` and `repo_head` are unchanged across both. A document description edited in the UI survives both. Both paths print the same block, including the `stop` line |
| 3 | Remove the project through the UI (Settings → Manage Projects → Remove Project), then `start` | Not resurrected: `projects: []` in settings, and `project.kiln` still on disk, which is why disk presence was the wrong gate. The three-cause warning fires and **no `ui_state` hint prints**, on the already-running path and after a `stop` alike |
| 4 | `reset` | Fixture back, the case-2 edit gone, project re-registered |

### Spend

`GET https://openrouter.ai/api/v1/key` reports **$0.02935** total usage on the
authoring key at the end of this phase, against its $2 limit. Phase 3 recorded
$0.029 for everything up to it, so phase 4's own spend is somewhere between zero and
a twentieth of a cent — the two figures are not far enough apart to separate, and no
attempt is made to. That it is that small is unsurprising in one direction and
measured in the other: extraction was passthrough and made no model call at all, and
the only paid work in the phase was six chunk embeddings plus one query embedding.

## Deviations from the plan

- **The documents were written twice.** At ~300 words each they produced exactly one
  chunk apiece, so nothing about chunking was visible in the fixture: `chunk_idx` was
  always 0, and a chunk viewer had one row to show. They were deleted through the UI,
  rewritten at ~550 words, re-uploaded, and the chain re-run. The alternative —
  shrinking the chunk size — was rejected because 512/64 is what the app's own
  templates use, and a fixture that departs from the default to make its own data look
  better is worth less as a reference.

  **`chunk_size` is counted in tokens, not words**, which matters for anyone sizing a
  corpus off these numbers. `FixedWindowChunker` hands it straight to llama_index's
  `SentenceSplitter`
  (`libs/core/kiln_ai/adapters/chunkers/fixed_window_chunker.py:19`), which tokenizes;
  the create-chunker form nonetheless describes it as "the approximate number of words
  to include in each chunk". Re-running that splitter over the three committed
  extractions measures 519 words → 658 tokens, 528 → 682, and 650 → 824, i.e. 1.27–1.29
  tokens per word for this prose, so the 512 setting cuts at roughly 400 words of it.
  The observed 300-words-to-one-chunk and 550-to-two holds either way, and it was the
  observation rather than the arithmetic that drove the rewrite.
- **The extractor names a model the fixture never calls.** `create_extractor_form.svelte`
  posts `passthrough_mimetypes: ["text/plain", "text/markdown"]` with no control over
  it, so markdown documents short-circuit in `BaseExtractor._should_passthrough`. The
  dropdown filters to `supports_doc_extraction`, which
  `deepseek/deepseek-v4-flash-0731` — the model every other phase used — is not, so
  the config names Gemini 3.5 Flash Lite via OpenRouter, the app's own recommended
  choice in the `cost_optimized` template. Nothing was substituted for a *failure*:
  no extraction call was ever made, cheaply or otherwise. Adding an HTML or PDF
  document to force a real extraction call was considered and rejected — it would have
  meant a paid vision call on a model outside the one this project standardised on, to
  exercise a code path the fixture does not otherwise need.
- **`lancedb_hybrid`, not `lancedb_fts`.** FTS would let a keyless sandbox *search*
  as well as index, which is tempting for a seed fixture. It would also mean the
  committed embeddings are used only to build the index and never to answer a query,
  which makes the fixture a worse demonstration of the thing this phase exists to
  prove. Hybrid is also the app's own recommended default.
- **No reranker.** The form offers one and the datamodel supports it, but a reranker
  needs a Cohere-compatible provider that this sandbox does not have. `reranker_config_id`
  stays null, which is what every built-in template also ships.

## Things worth knowing that are not deviations

- **A closed `Collapse` hides its fields from the accessibility tree.** The "Advanced
  Options" sections in the create-config dialogs are a checkbox plus a panel whose
  contents are `visibility: hidden` when closed — present in the DOM, absent from
  `snapshot` and `find`. So `find "Chunker Name"` returning nothing means the section
  is closed, not that the field is missing, and every click toggles it, so a click
  that looks like it did nothing followed by a second click lands you back where you
  started. Reading `input[type=checkbox].checked` inside the open dialog is what
  distinguishes the two. Recorded in `USING_PLAYWRIGHT.md`.
- **With no provider connected the RAG screens show raw model ids** — "Model ID:
  `gemini_3_5_flash_lite`" instead of "Gemini 3.5 Flash Lite". This is what a seeded
  sandbox looks like by default; connecting a provider restores the friendly names.
  Recorded in `USING_PLAYWRIGHT.md` so it is not mistaken for a rendering bug.
- **One run of the chain was started by a click this transcript cannot account for.**
  Two `playwright-cli click` calls were made with an empty ref (the shell capture that
  was supposed to fill them produced nothing), and the run nonetheless executed —
  `backend.log` shows exactly two `GET …/rag_configs/184180693413/run` calls for two
  intended runs. The resulting fixture was verified on disk rather than trusted:
  3 extractions against extractor `117940161350`, 3 chunked documents of 2 chunks
  each, 3 `ChunkEmbeddings` of 2 vectors of 1536 floats against embedding config
  `289999549185`. Which click actually landed is not something this document can
  establish, and no mechanism is asserted for it.
