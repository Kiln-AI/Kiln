---
status: complete
---

# Phase 2: experiments repo — stdio MCP server

**Repo:** `kiln-ai/experiments` (internal). Second PR. Pins `kiln-ai` core by the git rev of the Phase-1 kiln branch (the kiln_server precedent).

## Overview

Wrap the Phase-1 `MemoryStore` in a stdio MCP server so the O3 compile agent (Phase 0) can use the six memory tools from Claude Code. The server is a mechanical adapter — no memory logic lives in it. The tool description texts are spec'd deliverables (they are prompts). Concurrency is a feature: stdio means one server process per session, so parallel sessions are concurrent writers from separate processes — test that.

## Steps

1. **Server skeleton** (official MCP Python SDK, stdio transport), following experiments-repo conventions.
2. **Launch args:** `--project /path/to/project.kiln` (required — load the `Project`, construct `MemoryStore(project)`). It is the only arg: **no `--default-scope`, no scope defaults.** Missing/invalid `--project` is a clear startup error.
3. **Register six tools** with names/params identical to functional_spec §6 (`save_memory`, `list_memories`, `get_memories`, `update_memory`, `delete_memory`, `memory_summary`). Each body:
   - Call the matching `MemoryStore` method.
   - Serialize results with `model_dump()` (+ `exclude_none=True` so `untagged` drops when absent).
   - For `list_memories`, render the truncation nudge string from `remaining` + `remaining_tag_counts` (e.g. `"62 more — filter by tag: probe(18), api_quirk(9), …"`).
   - Convert `MemoryNotFoundError` / `InvalidContentMatchError` / Pydantic `ValidationError` into MCP tool errors (not crashes).
4. **Tool description texts** (functional_spec §6 / architecture §5.2) — author the six descriptions carrying the write discipline, `content_length: 0` meaning, `tags` AND-semantics + multi-call-for-OR, "call `memory_summary` at session start", "list before you save — update, don't duplicate", conditions-not-rules, "prefer `stale`-tag + correction over rewrites", "delete only confirmed junk", and the `"project"` / `"task::<id>"` scope conventions. Representative tags only — not a closed enum.
5. **README** with a Claude Code `.mcp.json` example (how to point Claude Code at the server + a project path).
6. **Pin kiln core** by the Phase-1 branch git rev.
7. **Tests + manual smoke test** (below).

## Tests

- **Per-tool round-trip** over stdio: each of the six tools accepts the §6 params and returns the expected shape (`save` echoes id+record; `list` sorted newest-first with `content_length`; `get` full records; `update` partial replace; `delete` removes; `summary` per-scope JSON matching functional_spec §8).
- **`list_memories` nudge rendering**: truncated result includes the "N more — filter by tag: …" text.
- **Launch args**: `--project` binds the store; omitting it errors at startup; there is no `--default-scope`.
- **Error mapping**: unknown id → tool error; invalid `content_match` regex → tool error; over-length `overview` on save → tool error. Server stays up.
- **Two-server-process concurrency** (the Phase-0 topology): two server processes on the same project folder append + update concurrently; all appends survive, same-record updates are last-writer-wins, every record parses.
- **Manual smoke test**: drive the server from a coding agent (Claude Code) against a scratch Kiln project; confirm save → summary → list → get → update → delete round-trips.
