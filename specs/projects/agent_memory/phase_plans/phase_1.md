---
status: complete
---

# Phase 1: kiln `libs/core` — datamodel + core memory API

**Repo:** `Kiln-AI/kiln` (off `main`). This is the first PR; the experiments MCP server (Phase 2) pins the git rev produced here.

## Overview

Build the `Memory` datamodel record, register it under `Project`, and build the store-agnostic `MemoryStore` API (the six operations). All of it is testable in `libs/core` with no adapter and no other repo. The load-safety invariant (a record that once saved never fails to load) and the concurrent-append guarantee (file-per-record) are the two things to get right.

## Steps

1. **`libs/core/kiln_ai/datamodel/memory.py`** — `Memory(KilnParentedModel)`:
   - Fields `overview` (`Field(max_length=140)`), `content` (`str | None`, `Field(default=None, max_length=2000)`), `tags` (`Field(default_factory=list)`), `scope` (`Field(...)` required). Field descriptions verbatim from project_overview.md "Datamodel sketch".
   - **No `name` field** (id-only child folders drop out of `build_child_dirname`).
   - Validators (architecture §2.4):
     - `overview` `mode="before"`: coerce to str if needed, `strip()`, reject empty, reject newline. (`max_length=140` enforces length on the stripped value.)
     - `content` `mode="before"`: `None` passthrough; else `strip()`, empty → `None`. (`max_length=2000` enforces length; newlines allowed.)
     - `scope` `mode="before"`: `strip()`, reject empty, reject newline, reject `len > 255`.
     - `tags`: `@field_validator("tags")` calling the **shared** `validate_tags` helper (see step 1b) — reject empty-string tags and tags containing spaces.
   - Confirm nothing fails on load for once-valid data (rules are monotonic; document the `loading_from_file` escape hatch is available but unused).

1b. **`libs/core/kiln_ai/utils/validation.py`** — add the shared `validate_tags(tags: list[str]) -> list[str]` helper (architecture §2.5). Reuse it in `Memory`. **Recommended, low-risk consolidation in the same PR:** migrate the four existing copies (`task_run.py`, `extraction.py`, `spec.py`, and the tag loop in `rag.py`) to the helper; reconcile `spec.py`'s lowercase error-message assertion. If the reviewer wants a narrower memory PR, the four-site consolidation can split into a follow-up commit, but the helper ships with `Memory`.

2. **`libs/core/kiln_ai/datamodel/project.py`** — register the relationship:
   - Add `"memories": ParentOfRelationship(model=Memory, filesystem_name="assistant_memory")` to `Project.parent_of`; import `ParentOfRelationship` and `Memory`.
   - Add the typed accessor `def memories(self, readonly: bool = False) -> list[Memory]: return super().memories(readonly=readonly)  # type: ignore`.

3. **`libs/core/kiln_ai/datamodel/__init__.py`** — `from kiln_ai.datamodel.memory import Memory`; add `"Memory"` to `__all__`.

4. **`libs/core/kiln_ai/memory/` package** (`__init__.py` + `memory_store.py`):
   - `MemoryStore(parent: KilnParentModel, memory_model: type[Memory] = Memory)` — raise if `parent.path is None`.
   - `_UNSET` sentinel; `MemoryNotFoundError`, `InvalidContentMatchError`.
   - `save_memory` / `get_memories` / `update_memory` / `delete_memory` / `list_memories` / `memory_summary` per architecture §3.2–3.4, using `all_children_of_parent_path(readonly=True)`, `from_ids_and_parent_path`, `from_id_and_parent_path`.
   - Pydantic result types `MemoryListing`, `MemoryListResult`, `ScopeSummary` (`untagged: int | None = None`), `MemorySummary` (architecture §3.5).
   - `list_memories`: AND-filter (scope exact / tags superset / `content_match` `re.IGNORECASE` over overview+content), newest-first stable sort (`(created_at, id)` reverse), page by `offset`/`limit`, `remaining` + `remaining_tag_counts` over the not-returned remainder, `content_length` = 0 for null content.
   - `memory_summary`: per-scope grouping, `count` / `newest` / `tags` (desc) / `untagged` (if > 0), scopes newest-first, `total`.
   - Export from `__init__.py`.

5. **Tests** (functional_spec §12.1–12.3; architecture §7):
   - `datamodel/test_memory.py` — field constraints, normalization, load-leniency, on-disk path `assistant_memory/{id}/memory.kiln`, round-trip.
   - `memory/test_memory_store.py` — all six ops, filtering/sort/paging, truncation counts, partial-update sentinel, `content=""` clears, unknown-id errors, summary shape.
   - `memory/test_memory_store_concurrency.py` — multi-process append/update (see Tests below).
   - Extend the project test file with `memories()` accessor + registration (id-only folder, backcompat empty list).

6. `uv run ./checks.sh --agent-mode`; fix anything introduced.

## Tests

**`Memory` datamodel**
- `test_overview_accepts_max_len` / `test_overview_rejects_over_len` / `test_overview_rejects_newline` / `test_overview_rejects_empty` / `test_overview_strips`
- `test_content_defaults_none` / `test_content_accepts_max_len` / `test_content_rejects_over_len` / `test_content_empty_becomes_none` / `test_content_allows_newlines` / `test_content_strips`
- `test_tags_default_empty` / `test_tags_reject_space` / `test_tags_reject_empty_string`
- shared helper: `test_validate_tags_helper_accepts_valid` / `test_validate_tags_helper_rejects_space_and_empty` (in `utils/test_validation.py`); if consolidating, confirm the four migrated models still reject bad tags
- `test_scope_required` / `test_scope_accepts_max_len` / `test_scope_rejects_over_len` / `test_scope_rejects_newline` / `test_scope_rejects_empty` / `test_scope_accepts_opaque_and_dangling`
- `test_saved_under_project_id_only_folder` (path is `assistant_memory/{id}/memory.kiln`, no name prefix)
- `test_roundtrip_save_load_equal`
- `test_load_leniency_once_valid_always_loads`
- `test_project_memories_accessor` / `test_project_no_memory_folder_returns_empty`

**`MemoryStore`**
- `test_save_returns_id_and_writes_file`
- `test_list_newest_first` / `test_list_scope_exact_filter` / `test_list_tags_and_semantics` / `test_list_content_match_regex_case_insensitive` / `test_list_limit_offset` / `test_list_content_length_zero_for_null`
- `test_list_truncation_remaining_and_tag_counts` / `test_list_no_truncation_when_page_covers_matched`
- `test_list_invalid_regex_raises`
- `test_get_single_and_many` / `test_get_unknown_ids_omitted`
- `test_update_partial_replace_only_provided` / `test_update_revalidates_provided_field` / `test_update_content_empty_clears_to_none` / `test_update_unknown_id_raises` / `test_update_last_writer_wins`
- `test_delete_removes_folder` / `test_delete_unknown_id_raises`
- `test_summary_per_scope_grouping` / `test_summary_tag_counts_desc` / `test_summary_untagged_only_when_nonzero` / `test_summary_scopes_newest_first` / `test_summary_scoped_call_single_block` / `test_summary_total`

**Concurrency**
- `test_multiprocess_appends_all_survive` — N processes each save M memories; final count == N*M, every file parses.
- `test_multiprocess_same_id_update_last_writer_wins` — concurrent updates to one id resolve to a single valid record (no corrupt merge).
