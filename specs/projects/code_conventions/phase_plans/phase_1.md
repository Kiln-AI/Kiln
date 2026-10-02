---
status: complete
---

# Phase 1: `kiln-conventions` skill for Kiln

## Overview

Add the `kiln-conventions` skill to Kiln: the canonical universal rules (`rules.md`), the canonical diff-based conventions gate (`conventions_gate.py` + tests), Kiln's gate config and allowlist, three area references, and the wiring that makes agents and reviewers use it. Calibrate the gate on the Kiln source roots and save the `history-comment` hit list as the work list for the phase 3 comment sweep.

All new files live in `.agents/skills/kiln-conventions/`. No runtime code changes.

## Steps

1. **`conventions_gate.py`** (stdlib only, Python ≥ 3.10, one file, no repo imports).
   - `Line` (frozen dataclass: `path`, `lineno`, `text`), `Hit` (`severity`, `rule`, `path`, `lineno`, `snippet`), `CheckConfig` (`enabled`, `severity`, `paths`, `exclude`), `Config` (`skip_globs`, `checks: dict[str, CheckConfig]`, `env_access_allowed`, `module_level_call_ignore`, `module_level_construct_patterns`), `AllowEntry` (`rule: str | None`, `pattern`), `Result` (`hits`, `allowlisted`).
   - `class GateError(Exception)` for exit-2 conditions.
   - Pure functions:
     - `glob_to_regex(glob) -> re.Pattern` and `path_matches(path, globs) -> bool` (`**/` = zero or more dirs, `*` doesn't cross `/`).
     - `parse_unified_diff(text) -> list[Line]` (tracks `+++ b/<path>` and `@@ … +start[,count] @@`; keeps `+` lines; skips `+++`, `\ No newline`, `-` lines; `+++ /dev/null` drops the file).
     - `lang_for_path(path) -> str | None` (`py`, `ts` for `.ts`/`.js`, `svelte`).
     - `extract_comment(text, lang) -> str | None` per the architecture's heuristics (Python `#` outside quotes; TS/JS/Svelte `//` not after `:` and not in quotes, `/* … */`, leading `*`, `<!-- … -->`, unclosed `/*` / `<!--`).
     - One `check_*(line, cfg) -> Hit | None` per rule: `history-comment`, `global-stmt`, `bool-env`, `env-access`, `core-config-shared`, `lib-imports-routes`, `module-level-call`, `module-level-construct`, `module-level-subscribe`; registered in a module-level `CHECKS` tuple of `(rule_id, langs, fn)`.
     - `HISTORY_PATTERNS` module tuple of compiled regexes, with the `used to` special case (`USED_TO_PATTERN` + preceding-word guard).
     - `load_config(path) -> Config` (exit-2 errors on missing file, bad JSON, unknown check id, bad severity, bad regex).
     - `load_allowlist(path) -> list[AllowEntry]` (missing file = empty; invalid regex = `GateError` naming the line).
     - `filter_lines(lines, cfg) -> list[Line]` (skip globs + supported extensions).
     - `run_checks(lines, cfg, allow) -> Result` (sorted by path, line).
     - `format_result(result) -> str` (`SEV\tRULE\tpath:line\tsnippet`, snippet stripped and cut to 160 chars, last line `conventions_gate: <n> FAIL, <m> WARN, <k> allowlisted`).
   - IO functions: `git(repo, *args) -> str` (raises `GateError` with git's stderr), `collect_range`, `collect_worktree` (diff vs HEAD + untracked files read whole), `collect_files` (directories expand via `git ls-files -- <dir>`), `read_whole_file` (skip undecodable/unreadable).
   - `main(argv: list[str] | None = None) -> int` with argparse: mutually exclusive `--range RANGE` / `--worktree` / `--files PATH...`, plus `--repo`. Default repo = `git rev-parse --show-toplevel`. Config and allowlist read from the script directory (overridable via `--config-dir` for tests only if needed; prefer passing `script_dir` to an internal `run(...)`). Usage errors exit 2 (argparse already exits 2).
   - `if __name__ == "__main__": sys.exit(main())`.

2. **`gate_config.json`** (Kiln data): skip globs (tests, `__tests__`, `conftest.py`, `api_schema.d.ts`, the generated `kiln_ai_server_client`, build output); `.agents/**` stays in scope and is allowed for env access. All checks enabled, with paths scoped per the architecture (`core-config-shared` → `libs/core/kiln_ai/**`, `lib-imports-routes` / `module-level-subscribe` → `app/web_ui/src/lib/**`). `env_access_allowed` adjusted to the real config modules and entry points. `module_level_call_ignore` (e.g. `include_router`) and `module_level_construct_patterns` set from calibration.

3. **`gate_allow.txt`**: header explaining the format; entries only for calibrated true-negatives that can't be fixed by tuning a pattern (each with a `#` reason).

4. **`test_conventions_gate.py`**: imports the gate by path, fixture config in `tmp_path`, covers the cases listed below.

5. **Calibration**: run `--files libs/core/kiln_ai libs/server/kiln_server app/desktop app/web_ui/src`; count per rule; sample `history-comment` hits and tighten/remove noisy patterns; time a typical range run; save the final `history-comment` hits to `specs/projects/code_conventions/research/history_comment_baseline.txt`.

6. **`rules.md`**: rules A–H from functional spec §4 (23 rules), each a one-line imperative, ≤ 1 line of why, one ❌/✅ example; gate-enforced rules tagged `(gate: <id>)`. Carries the content of the AGENTS.md "Code Comments" section (what to comment, what never to write, docstrings describe the contract). No repo-specific paths.

7. **`SKILL.md`** (≤ ~120 lines): frontmatter (`name: kiln-conventions`, triggering `description`), flow (read rules → area refs → write → gate → self-check review-only rules), path → reference table, "UI changes also load `kiln-ui`", end-of-task WARN reporting, "Maintaining the gate" (test command, shared files, known limitations).

8. **References** `references/core.md`, `server_desktop.md`, `web_ui.md`: Gotchas / Where things go / Startup sections covering the topics listed in functional spec §4. Every symbol verified with `git grep` against the current branch; no line numbers; nothing about bugs with open fix PRs (check `gh pr list` for Config bool parsing etc.).

9. **Wiring**:
   - `AGENTS.md`: "Agent Prompts" gets the invoke-`kiln-conventions` line; the "Code Comments" section collapses to a pointer to `rules.md` §A (its content now lives there).
   - `.agents/code_review_guidelines.md`: add the apply-rules-and-run-gate line near the top; replace the "Code comments" and "Editing globals" bullets with that pointer.
   - `.agents/skills/kiln-ui/SKILL.md`: one-line pointer to `kiln-conventions` → `references/web_ui.md`.
   - Run `.agents/claude/setup.sh` to regenerate local `CLAUDE.md` / `.claude/skills` (untracked).

## Tests

All in `.agents/skills/kiln-conventions/scripts/test_conventions_gate.py`, run with `uv run python -m pytest .agents/skills/kiln-conventions/scripts/test_conventions_gate.py`.

- `test_parse_unified_diff_multi_hunk`: two hunks, correct new line numbers, context-free `-U0`.
- `test_parse_unified_diff_new_file`, `..._rename`, `..._no_newline_marker`, `..._ignores_deletions`, `..._deleted_file`.
- `test_extract_comment` (parametrized): Python `#` inside strings ignored; trailing `#` comment; TS `//` comment; URL `https://` not a comment; `//` inside quotes; `/* */` same line; JSDoc `*` line; `<!-- -->`; unclosed `/*` and `<!--`; code-only line → `None`.
- `test_history_patterns_hit` (parametrized over every pattern) and `test_history_patterns_false_positive_guards` ("is used to compute", "now returns", "moved to", "instead of", "were used to").
- One hit + one non-hit per check: `global-stmt`, `bool-env`, `env-access` (allowed path vs not), `core-config-shared` (in vs outside `libs/core/kiln_ai`), `lib-imports-routes` (static + dynamic import, `lib/` vs `routes/` file), `module-level-call` (bare call, indented call, keyword line, ignore regex, `if __name__` block), `module-level-construct`, `module-level-subscribe`.
- `test_history_comment_only_scans_comments`: phrase in code/string is not a hit.
- Path scoping: `skip_globs` (test files, generated), unsupported extension dropped, check `paths`/`exclude`, `glob_to_regex` `**/` zero-dir case.
- Allowlist: unscoped entry silences any rule; `RULE:` entry silences only that rule; comments/blanks ignored; invalid regex → exit 2 naming the line.
- Config errors: missing config → exit 2; unknown check id → exit 2; check missing from config is disabled.
- `format_result`: line format, 160-char snippet cut, sort order, summary line.
- End-to-end via `main()` in a temp `git init` repo: `--range` (only added lines reported), `--worktree` (modified + untracked file), `--files` (file and directory), exit 0 / 1 / 2 (bad range, not a repo).
