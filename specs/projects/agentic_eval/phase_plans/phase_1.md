---
status: complete
---

# Phase 1: Trace Toolset v1

## Overview

Build the self-contained, frozen trace toolset v1 under `libs/core/kiln_ai/adapters/eval/trace_tools/`: the `TraceView` canonicalization, the five tools (`trace_overview`, `preview_messages`, `read_messages`, `read_message_text`, `search_trace`), search with a time limit, the 40,000-character response limit with refusals, and the error catalog. Add the version dispatch (`trace_toolset()`) and the judge's Jinja environment (`judge_template_env()`), which binds the version-specific `trace_overview` filter. Tests cover every rule in the component doc, golden files freeze the v1 output (with an update flag), and benchmarks check the 20 MB performance targets.

No judge wiring: `LlmJudgeEval`, the datamodel field, the placeholder filter in `jinja_engine`'s base environment, the API and the UI are later phases.

## Steps

1. **`v1/limits.py`**: the frozen numeric limits from component §3.3 (`RESPONSE_CHARS = 40_000`, preview, read, text, numbers, search, overview limits).

2. **`v1/errors.py`**: `class TraceToolUsageError(ToolCallError)`, raised for every catalog error (E1–E11) and refusals. The adapter returns its message to the model as an error tool result.

3. **`v1/view.py`**: canonicalization (component §2).
   - `Part = Literal["content", "reasoning", "tool_calls"]`, `PARTS`, `FILTERABLE_ROLES`.
   - Frozen dataclasses `ToolCallRef(name, arguments, call_id, result_number)`, `MessageView(number, role, content, reasoning, tool_calls_text, tool_calls, tool_name, is_error)` with `part(part)`, `total_chars`, `non_empty_parts()`, and `TraceView(messages)` with `count`, `message(number)`, `part_text(number, part)`.
   - `build_view(trace: Sequence[Mapping[str, Any]]) -> TraceView`: two passes. Pass 1 canonicalizes each message (role mapping, list content parts, Kiln task-tool `output` extraction, refusals, `task_response` as content, call argument canonicalization, legacy `function_call`) and indexes calls by id. Pass 2 resolves tool result names (`unknown tool` when unresolved, legacy `name` for `function` messages) and sets each call's `result_number` (first result wins). Never raises on odd shapes.

4. **`v1/render.py`**: pure rendering.
   - Formatting helpers: `fmt_number`, `fmt_count`, `approx_tokens`, `quote`, `short_label`, `long_label`, `roles_suffix`, the continuation marker. Non-ASCII characters (en dash, em dash, ×, ·, →) are named constants written as escapes, so ruff's confusable-character rule stays clean.
   - Shared argument checks: `resolve_range` (E1, E2), `check_message_number` (E1), `check_filters` (E4), `check_numbers_or_range` (E3).
   - `Unit`, `RefusalContext(style, advice, fit_footer)` and `assemble(units, header, footer, refusal)`: joins units, or raises the §5 refusal with the largest fitting prefix and the tool's fit line and advice.
   - Frozen argument dataclasses `PreviewArgs`, `ReadArgs`, `TextArgs` with defaults applied (`end=None` means the last message).
   - `render_overview(view)`, `preview_messages(view, args)`, `read_messages(view, args)`, `read_message_text(view, args)` per component §4.1–4.4, including the selection rule, the "Not shown" footer, per-part and per-call-argument cut markers with exact continuation offsets, and result pointers.

5. **`v1/search.py`**: `SearchArgs` and `search_trace(view, args, *, timeout_seconds=SEARCH_TIMEOUT_SECONDS)` per component §6: literal (`regex.escape`) or regex compile with `VERSION0` and optional `IGNORECASE` (E7, E10), one deadline per call with the remaining time passed to each `finditer` (E8), zero-length matches skipped, full counting with only the requested page kept in memory, E9, header, footer, context snippets and the search refusal.

6. **`v1/definitions.py`**: frozen tool names, exact descriptions and JSON schemas (component §4), as `ToolDefinition(name, description, parameters)` in the fixed order, plus `tool_definition(name)`.

7. **`v1/tools.py`**:
   - `parse_args(tool_name, kwargs)`: re-validates against the tool's schema with `jsonschema` (E11), coerces integer-valued floats to `int`, de-duplicates `roles`/`parts`, applies defaults, checks E3. Returns the tool's args dataclass, or `None` for `trace_overview`.
   - `_TraceTool(UnmanagedKilnTool)` holding the view, and five subclasses. `run()` parses arguments and runs the pure function; `read_messages` and `search_trace` run in `asyncio.to_thread`. Ids are `build_kiln_unmanaged_tool_id("trace_v1_<name>")`. Schemas are deep-copied per tool so no caller can mutate the frozen definitions.
   - `build_tools(view) -> list[KilnToolInterface]` in the fixed order.

8. **`v1/__init__.py`**: `TraceToolsetV1`, a stateless frozen dataclass with `version` (1), `build_view`, `render_overview` and `build_tools`. The latter two accept any view object and raise `TypeError` for a view this version didn't build. `TOOLSET_V1 = TraceToolsetV1()`. v1 imports nothing from other versions or from the top-level `trace_tools` modules.

9. **`trace_tools/toolset.py`**: `TraceViewProtocol` (opaque), `TraceToolset` protocol (`version`, `build_view`, `render_overview`, `build_tools`), `UnsupportedTraceToolsetVersion(version)`, and `trace_toolset(version)` dispatching with a function-local import of v1.

10. **`utils/jinja_engine.py`**: add a public `template_env_with_filters(filters) -> Environment` that returns an overlay of the template environment with a new filters dict (the overlay otherwise shares the parent's dict). This keeps the overlay detail next to the private `_template_env` instead of importing it from another package.

11. **`trace_tools/template_env.py`**: `judge_template_env(toolset, trace, view) -> Environment`, binding `trace_overview` to a per-environment closure. Called with the judge's own `trace` (identity check), it reuses `view`, or builds it once on first use when `view` is `None`. Any other list of dicts gets a fresh view. Anything else raises `JinjaExtractionError`.

12. **`trace_tools/__init__.py`**: re-export `TraceToolset`, `TraceViewProtocol`, `UnsupportedTraceToolsetVersion`, `trace_toolset`, `judge_template_env`.

13. **`v1/conftest.py`**: `--update-trace-tool-goldens` option; a seeded, dependency-free synthetic coding-agent trace generator (an LCG, not `random`, so it never changes across Python versions); fixtures loading the handcrafted golden traces.

14. **`v1/golden/`**: handcrafted traces (`traces/coding_agent.json`, `traces/edge_cases.json`), `cases.json` (`id`, `trace`, `tool`, `args`, optional `raises`), `expected/<id>.txt`, and `definitions.json`.

## Tests

- `v1/test_view.py`
  - `test_view_numbers_from_one_including_system`: numbering and the role mapping table (`function` → `tool`, missing or non-string → `unknown`, other strings kept).
  - `test_view_content_list_parts`: text joined with newlines; `[image]`, `[audio]`, `[file]`, `[refusal] text`, `[<type>]`; non-dict and type-less entries skipped.
  - `test_view_kiln_task_tool_output_extracted`: `{"output": ...}` replaced for tool results only; non-JSON, non-object and non-string `output` kept as-is.
  - `test_view_task_response_is_content_not_call`: alone and after text; last one wins; excluded from `tool_calls`.
  - `test_view_assistant_refusal_appended`.
  - `test_view_tool_args_canonicalized`: JSON re-serialized, non-JSON kept, non-string dumped, missing → `""`.
  - `test_view_tool_name_resolution`: matched, unmatched and missing id (`unknown tool`), legacy `function` name, two results for one call id (first wins), call with no result.
  - `test_view_legacy_function_call_counts_as_call`.
  - `test_view_loose_dicts_never_raise`: non-dict messages, wrong types everywhere, non-list `tool_calls`, non-dict `function`.
  - `test_view_sizes_and_part_text`.
- `v1/test_render.py`
  - `test_approx_tokens_buckets`, `test_fmt_count`, `test_quote_escaping_and_truncated_marker`.
  - `test_overview_format`, `test_overview_empty_trace`, `test_overview_top_tools_overflow`, `test_overview_omits_lines_without_data`, `test_overview_largest_ties_by_number`.
  - `test_preview_line_pieces` (parametrized over each piece, `preview_chars=0`, ` ×k`, ERROR), `test_preview_no_match`, `test_preview_range_and_roles`.
  - `test_range_errors` (E1 for start and end, empty trace, E2), `test_unknown_filter_values` (E4).
  - `test_read_selection_requires_requested_part`, `test_read_numbers_footer_reasons`, `test_read_numbers_and_range_conflict`, `test_read_no_match_with_footer`, `test_read_header_sizes_not_shown`, `test_read_body_order`.
  - `test_read_cut_markers_point_to_continuation`: content, reasoning and per-call argument markers; calling `read_message_text` at each offset continues the text exactly.
  - `test_read_call_result_pointers`: ok, ERROR, no result.
  - `test_text_window_and_continuation`: header, window, marker; `offset` at the last char; `max_chars=40000`; E5 (and the empty-message variant); E6.
  - `test_refusal_fit_range_*`: just under returns, just over refuses; range and numbers fit lines; `k = 0`; a single message alone too big.
- `v1/test_search.py`
  - `test_search_literal_vs_regex`, `test_search_case_sensitivity`, `test_search_offsets_match_read_message_text`, `test_search_context_snippet_edges`, `test_search_paging_count_offset` (header, footer, E9), `test_search_zero_length_matches_skipped`, `test_search_invalid_regex` (E7), `test_search_timeout` (E8 with a catastrophic pattern and a small injected timeout), `test_search_empty_pattern` (E10), `test_search_part_order_and_filters` (reasoning only when requested, roles, start/end), `test_search_no_matches`, `test_search_refusal_count_fits`.
- `v1/test_tools.py`
  - `test_tool_definitions_order_and_ids`: five tools in order, `kiln_unmanaged::trace_v1_*` ids, schemas valid.
  - `test_parse_args_defaults_and_coercion`, `test_parse_args_invalid` (E11, parametrized), `test_parse_args_e3`.
  - `test_tool_usage_errors_are_tool_call_errors`: each tool raises `TraceToolUsageError` for usage errors.
  - `test_tools_run_returns_output`: each tool returns a `ToolCallResult`.
  - `test_tool_schema_is_a_copy`: mutating one tool's schema leaves the definitions intact.
  - `test_judge_loop_continues_after_tool_error`: through the real `LiteLlmAdapter` with a scripted model, a bad call is followed by a good one and the run completes.
  - `test_toolset_v1_rejects_foreign_view`.
- `v1/test_golden.py`
  - `test_golden_cases`: every case in `golden/cases.json` matches its expected output (or error text) exactly; rewrites them with `--update-trace-tool-goldens`.
  - `test_golden_definitions`: tool names, descriptions and schemas match `golden/definitions.json`.
  - `test_golden_overview_filter_matches_tool`: the `trace_overview` filter in `judge_template_env` renders exactly the `trace_overview` golden output for each fixture trace.
- `v1/test_perf.py` (benchmarks on a seeded synthetic 20 MB trace)
  - `test_bench_build_view_20mb`, `test_bench_preview_whole_trace_refused_20mb`, `test_bench_search_20mb`: bounds from architecture §6 with slack for CI.
- `trace_tools/test_toolset.py`
  - `test_trace_toolset_dispatch`, `test_trace_toolset_unsupported_version`.
  - `test_judge_template_env_reuses_prebuilt_view`, `test_judge_template_env_builds_view_once_when_none`, `test_judge_template_env_other_list_gets_own_view`, `test_judge_template_env_rejects_non_message_lists`, `test_judge_template_env_keeps_base_env_and_other_filters`.
- `utils/test_jinja_engine.py`
  - `test_template_env_with_filters_overlays_without_mutating_base`.
