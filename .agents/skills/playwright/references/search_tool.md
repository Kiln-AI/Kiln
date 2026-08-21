# The search tool, and what a keyless sandbox can do with it
Worth its own paragraph, because it is the one part of the fixture whose data is
split between the repo and your machine.

The fixture commits the *outputs* of running the RAG chain, not just its configs:
each document carries its extraction, its chunks, and its embeddings, all inside the
project directory and therefore all captured by `snapshot`. What it does not commit
is the LanceDB index, which lives at `.kiln_ai/rag_indexes/lancedb/<rag_config_id>`
inside the sandbox home — outside the project, and derived data. Kiln's git sync
draws the same line.

So a freshly seeded sandbox opens Docs & Search showing extraction, chunking and
embedding complete and **indexing at zero**. Press Run on the search tool and the
index builds from the committed embeddings, with no API key and no network. That is
worth knowing before you conclude a keyless sandbox cannot exercise RAG at all.

Searching is the part that does need a key: the vector store is `lancedb_hybrid`, and
a hybrid or vector query embeds the query string live. A full-text-only store would
not. Connect OpenRouter through Settings → Providers and the tool's own Search panel
returns chunks from the seeded documents.

Two things about the chain that read like bugs and are not:

- **The extractor names a model it never calls.** The create-extractor form hardcodes
  `passthrough_mimetypes` to `text/plain` and `text/markdown`, and the fixture's
  documents are markdown, so every extraction is a passthrough copy with
  `source: passthrough`. The model in the config would only matter for a PDF or an
  image.
- **With no provider connected, model names render as raw ids** — "Model ID:
  `gemini_3_5_flash_lite`" rather than "Gemini 3.5 Flash Lite". Connecting a provider
  restores the friendly names.

