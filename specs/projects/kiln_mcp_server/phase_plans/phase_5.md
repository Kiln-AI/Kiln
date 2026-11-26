---
status: complete
---

# Phase 5: API reference pipeline and the skill-tree check

## Overview

The skill's API reference (`references/knowledge/api_docs/`) is generated for the first time, by the pinned `openapi2skill` from an in-process dump of the desktop app's OpenAPI document with the MCP-blocked operations removed, plus a catalogue index `api_index.md`. A CLI regenerates and checks it, and a CI step and `checks.sh` fail when it is stale. The skill-tree check (`tree_check.py`) checks every path written in the skill, the file and front-matter rules, the wording rules, and reachability from `SKILL.md`. The placeholder `SKILL.md` names the catalogue index so that the generated folder is reachable.

Spec: [skill_and_content](../components/skill_and_content.md) sections 3 (placeholder line), 5, 6, 8 and the step-4 rows of 10; architecture sections 6 (step 4) and 9.2.

## Steps

1. **Generator pin.** Root `pyproject.toml`: dev group `"openapi2skill ; python_full_version >= '3.13'"`; `[tool.uv.sources] openapi2skill = { git = "https://github.com/scosman/openapi2skill", rev = "c7c2ca55e5b5300e28678ba4e47e2ad6f5bd1d28" }`. `uv lock`.

2. **`skill_files.py`**: expose the walk as `list_tree(root: Traversable) -> dict[str, Traversable]` (same skip rules), used by `build_index` and by the tree check, so both see the same files.

3. **`skill_checks/__init__.py`** (empty docstring module), **`skill_checks/api_reference.py`**:
   ```python
   ALLOWED_METHODS = ("get", "post", "patch", "delete")
   TARGET = "references/knowledge/api_docs"
   GENERATOR_COMMAND = (sys.executable, "-m", "openapi2skill")
   class ApiReferenceError(Exception)
   def endpoint_doc_name(method: str, path: str) -> str
   def drop_blocked(spec: dict) -> dict          # also stops on a method outside ALLOWED_METHODS
   def normalise(spec: dict) -> dict             # info.version = "0.0.0"
   def run_generator(spec: dict, workdir: Path, *, command: Sequence[str] = GENERATOR_COMMAND) -> dict[str, bytes]
   def catalogue_index(spec: dict, files: Mapping[str, bytes]) -> bytes
   def render(spec: dict) -> dict[str, bytes]
   def write_folder(files: Mapping[str, bytes], target: Path) -> None
   def diff_folder(files: Mapping[str, bytes], target: Path) -> list[str]
   ```
   `run_generator` writes the spec JSON, runs the generator with `PYTHONUTF8=1` and a fixed `PYTHONHASHSEED` (the generator iterates a set of method names, so its row order otherwise changes from run to run), stops on a non-zero exit or a `Warning: filename collision` stderr line, reads the single output folder's `reference/` files, normalises newlines, and stops when the endpoint-doc count differs from the operation count. `catalogue_index` writes a heading, one sentence and the table `| Catalogue | Area | Endpoints | What it covers |`, rows in the spec's tag order (then first-encounter order, as the generator does).

4. **`app/desktop/skill_api_reference.py`**: `current_spec()` (sets `KILN_SKIP_REMOTE_MODEL_LIST=true`, returns `make_app().openapi()`), `main(argv) -> int` with `generate | check` and `--spec FILE`. Below Python 3.13: `check` prints `skipped: the generator needs Python 3.13` and exits 0, `generate` exits 2. `check` prints each diff line and the fix command and exits 1 on a difference. Output through `sys.stdout.write` / `sys.stderr.write`. Add the file to the conventions gate's `env_access_allowed` (it is an entry point).

5. **Generate the folder**: `uv run python -m app.desktop.skill_api_reference generate`. Commit `skill/references/knowledge/api_docs/` (25 catalogues, 243 endpoint docs, `api_index.md`).

6. **Placeholder `SKILL.md`**: one line that names `references/knowledge/api_docs/api_index.md` as the start of the API reference.

7. **`skill_checks/docs_index.py`**: `online_url_for(path: str) -> str` (section 4.2), used by `tree-front-matter`. The docs index renderer comes with `build`.

8. **`skill_checks/tree_check.py`**:
   ```python
   TREE_RULES: tuple[str, ...]            # the 11 rule ids of section 8
   BANNED_TERMS: dict[str, tuple[str, ...]]   # scope -> terms (section 9 table)
   TEST_SPLIT_READERS: tuple[str, ...] = ()   # filled by the content phase
   IGNORED_REFS: frozenset[tuple[str, str]]   # (file, path), each with a comment
   @dataclass(frozen=True) class Problem: rule: str; path: str; message: str
   @dataclass(frozen=True) class PathRef: line: int; raw: str; path: str; is_folder: bool; source: str
   def default_root() -> Path
   def tree_paths(root: Path) -> frozenset[str]
   def paths_in(text: str, *, file: str, tree: frozenset[str]) -> list[PathRef]
   def check_tree(root: Path) -> list[Problem]
   ```
   Path extraction (links, backticked spans, bare tokens, catalogue last column), normalisation, placeholders and the allowed exceptions as section 8 states them; the rules `tree-path`, `tree-relative`, `tree-bare-name`, `tree-call-syntax`, `tree-banned-term`, `tree-app-link`, `tree-split-pointer`, `tree-test-split`, `tree-front-matter` (table 4.2; the knowledge documents themselves are left to the knowledge check), `tree-file`, `tree-unreachable` (breadth-first from `SKILL.md`; more than 20 unreached in one folder give one line with a count and the first five). `Problem` lives here until the knowledge tooling port adds `knowledge_schema.py`.

9. **`skill_checks/__main__.py`**: `check [--root DIR]` prints `rule  path  message` per problem; exit 0 clean, 1 problems, 2 missing folder. The `build` command comes with the knowledge index builder.

10. **Wiring**: `Makefile` target `api_docs`; `checks.sh` `start_check "api reference" ...` beside `openapi schema`; `.github/workflows/check_api_bindings.yml` step "Check API reference" after the annotations check; `AGENTS.md` rows for the API reference check (fix: generate) and the skill-tree check; `server_desktop.md` gotcha: a route change also regenerates the API reference.

## Tests

- `skill_checks/test_api_reference.py`:
  - `test_drop_blocked_removes_operations_and_empty_paths`
  - `test_other_method_stops`
  - `test_version_is_normalised` (and the input is not changed)
  - `test_endpoint_doc_name`
  - `test_catalogue_index_rows` (tag order, counts, descriptions on one line, `|` escaped, a tag outside the tags array last)
  - `test_write_folder_replaces_whole_folder`
  - `test_diff_folder_reports_added_removed_changed`
  - `test_collision_warning_stops` (fake generator)
  - `test_generator_failure_stops`, `test_endpoint_count_mismatch_stops`, `test_newlines_are_normalised_and_skill_md_ignored` (fake generator)
  - `test_render_with_the_real_generator` (skips below 3.13; small spec, two runs give the same bytes)
- `skill_checks/test_tree_check.py` (synthetic trees): `test_unresolved_path_fails`, `test_wrong_case_path_fails`, `test_relative_link_fails`, `test_bare_name_fails`, `test_bare_name_in_link_label_passes`, `test_catalogue_bare_name_resolves`, `test_placeholder_is_skipped`, `test_path_in_fence_is_checked`, `test_anchor_and_folder_links_resolve`, `test_call_syntax_fails`, `test_app_path_without_origin_fails`, `test_api_path_is_not_an_app_link`, `test_split_wording_needs_the_pointer`, `test_test_split_request_fails`, `test_test_split_reader_needs_the_pointer`, `test_front_matter_by_type`, `test_unreachable_file_fails`, `test_non_markdown_file_fails`; plus `test_banned_terms_by_scope`, `test_product_name_is_not_banned`, `test_ignored_refs_are_skipped`, `test_many_unreachable_files_in_one_folder_are_one_line`, `test_a_clean_tree_has_no_problem`.
- `skill_checks/test_docs_index.py`: `test_online_url_for`.
- `skill_checks/test_main.py`: clean exit 0, problems exit 1 with `rule  path  message` lines, missing folder exit 2.
- `skill_checks/test_shipped_skill.py`: `PENDING_RULES`; `test_the_shipped_tree_passes_every_check`, `test_the_catalogue_index_exists`, `test_no_file_over_body_limit` (empty allow-list).
- `app/desktop/test_skill_api_reference.py`: `test_the_committed_api_reference_is_current` (skips below 3.13; `slow`), `test_committed_docs_match_the_block_list` (all versions), `test_check_below_3_13_skips`, `test_generate_below_3_13_is_a_usage_error`, `test_check_reports_a_stale_folder` and `test_generate_writes_the_folder` (with `--spec` and a fake `render`).
