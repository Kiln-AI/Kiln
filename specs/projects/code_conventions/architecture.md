---
status: complete
---

# Architecture: Code Conventions Skills

The project is small: two skills (markdown), one shared Python script with tests, a sync script, and doc wiring. Everything fits in this doc, so there are no component designs.

## 1. File layout

### Kiln (canonical)

```
.agents/skills/kiln-conventions/
  SKILL.md                    # entry point an agent loads
  references/
    rules.md                  # universal rules (shared, canonical)
    core.md                   # libs/core
    server_desktop.md         # libs/server + app/desktop
    web_ui.md                 # app/web_ui
  scripts/
    conventions_gate.py       # gate script (shared, canonical)
    test_conventions_gate.py  # gate tests (shared, canonical)
    gate_config.json          # Kiln-specific gate settings (not shared)
    gate_allow.txt            # Kiln allowlist (not shared)
```

### kiln_server

```
.agents/skills/kiln-server-conventions/
  SKILL.md
  references/
    rules.md                  # synced copy (header added by sync)
    api.md                    # the API service
    jobs_pipelines.md         # jobs, pipelines and optimizers
  scripts/
    conventions_gate.py       # synced copy (header added by sync)
    test_conventions_gate.py  # synced copy (header added by sync)
    gate_config.json          # kiln_server-specific
    gate_allow.txt
utils/sync_conventions.sh     # copies the shared files from a Kiln checkout
```

## 2. `conventions_gate.py`

### Constraints
- Python ≥ 3.10, stdlib only. It must run with `uv run python …` in both repos and with plain `python3`.
- One file. No imports from either repo.
- Byte-identical in both repos. The sync header is a leading comment block that `--check` strips.
- Fast: a typical PR diff in under 2 s. Shell out to `git` at most a few times per run.

### CLI
```
python conventions_gate.py --range <git-range> [--repo <path>]
python conventions_gate.py --worktree [--repo <path>]
python conventions_gate.py --files <path>... [--repo <path>]
```
- `--repo` defaults to `git rev-parse --show-toplevel` of the cwd. All reported paths are repo-relative.
- `gate_config.json` and `gate_allow.txt` are read from the script's own directory. If the config is missing, exit 2 with a clear message.
- **Exit codes:**
  - 0: no FAIL.
  - 1: at least one FAIL.
  - 2: usage, config or git error.
- **Output:** one line per hit, `SEV\tRULE\tpath:line\tsnippet`. The snippet is the stripped line, cut to 160 chars. Hits are sorted by path and line. A last line reads `conventions_gate: <n> FAIL, <m> WARN, <k> allowlisted`.

### Collecting lines
The internal model is a list of `Line(path: str, lineno: int, text: str)`.

- **range:** `git -C repo diff -U0 --no-color --no-ext-diff --diff-filter=AMR <range>`. Parse the `+++ b/<path>` and `@@ … +start[,count] @@` headers and keep the `+` lines with their new line numbers. Skip `+++` lines and `\ No newline` markers.
- **worktree:** the same with `diff -U0 HEAD`, plus every file from `git ls-files --others --exclude-standard`, read whole.
- **files:** every given file, read whole. A directory argument expands recursively to tracked files under it, via `git ls-files -- <dir>`.
- Files that can't be decoded as UTF-8 are skipped silently.
- **Path filtering** happens before any check:
  - drop paths that match any `skip_globs` entry in the config (tests, generated files);
  - keep only extensions that some check handles (`.py`, `.ts`, `.js`, `.svelte`).

  Globs are matched with `fnmatch` against the repo-relative path. `**` is handled by translating the glob to a regex in which `**/` matches zero or more directories.

### Comment extraction (for `history-comment`)
This is a per-line heuristic: the gate sees single added lines, not parse trees.

- **Python:** text after the first `#` that is outside a string literal. Find it by scanning the line while tracking `'`/`"` quote state; the triple-quote state across lines isn't tracked. Docstrings are not scanned in v1 (a known limitation; see §6).
- **TS/JS/Svelte:**
  - text after `//`, unless the `//` comes right after `:` (URLs) or sits inside a quote;
  - text inside `/* … */` on the same line;
  - a line whose stripped form starts with `*` (JSDoc continuation);
  - text inside `<!-- … -->` (Svelte);
  - a line that starts with `/*` or `<!--` without closing contributes the rest of that line.

### Checks
Every check is a small function `check_x(line: Line, cfg: Config) -> Hit | None`, registered in one list.

**Path scoping.** Each check has an id. `cfg.checks[id]` holds `{"enabled": bool, "severity": "FAIL"|"WARN", "paths": [globs], "exclude": [globs]}`, where empty `paths` means all paths. The per-rule data (phrase list, allowed paths, ignore regexes) lives in the config too, except the phrase list, which is a module constant so it stays shared.

| Rule id | Default sev | Match |
|---|---|---|
| `history-comment` | FAIL | Comment text (above) matches any `HISTORY_PATTERNS` entry (case-insensitive) |
| `global-stmt` | FAIL | py: `^\s*global\s+\w` |
| `bool-env` | FAIL | py: `bool\(\s*os\.(getenv|environ)` |
| `env-access` | FAIL | py: `os\.getenv\(` or `os\.environ\b`, unless the path matches `env_access_allowed` |
| `core-config-shared` | FAIL | py: `Config\.shared\(\)`, paths `libs/core/kiln_ai/**` (Kiln only; disabled in kiln_server config) |
| `lib-imports-routes` | FAIL | ts/svelte under `app/web_ui/src/lib/**`: `(from\s+|import\(\s*)["'][^"']*\broutes/` (Kiln only) |
| `module-level-call` | WARN | py: column-0 line matching `^[A-Za-z_][\w.]*\s*\(`, not starting with a keyword (`if|for|while|with|try|def|class|return|async|await|assert|raise|del|import|from|elif|else|except|finally|match|case|lambda|pass|yield`), and not matching any `module_level_call_ignore` regex |
| `module-level-construct` | WARN | py: column-0 assignment `^[A-Za-z_][\w.]*\s*(:[^=]+)?=\s*(.+)` whose RHS matches any `module_level_construct_patterns` regex (e.g. `\bSettings\(`, `\bmake_app\(`, `\bcreate_app\(`, `Config\.shared\(`, `AsyncClient\(`, `\.Client\(`, `create_engine\(`) |
| `module-level-subscribe` | WARN | ts under `app/web_ui/src/lib/**`: `^[A-Za-z_$][\w$.]*\.subscribe\(` at column 0 (Kiln only) |

**`HISTORY_PATTERNS`** is a module-level tuple of compiled regexes. The starting set:
- `\bno longer\b`
- `\bpreviously\b`
- `\bformerly\b`
- `\bvestigial\b`
- `\bbumped (?:from|to)\b`
- `\bswitched (?:from|to)\b`
- `\bchanged from\b`
- `\bwas (?:renamed|removed|moved|replaced)\b`
- `\b(?:after|before) the (?:refactor|fix|migration|rewrite)\b`
- `\bthe old (?:behaviou?r|code|implementation|approach|way|version)\b`
- `\b(?:in|as of) this (?:pr|change|commit)\b`
- `\bphase \d+\b`
- `\bfunctional[_ ]spec\b`
- `§`
- `\(P\d\)`
- `\bused to\b` (special-cased: rejected when the preceding word is one of `is|are|be|been|being|was|were|get|gets|got`, so "is used to compute" doesn't hit)

The coding agent calibrates this list (§5). Bare "now", "moved to" and "instead of" are deliberately excluded because they produce too many false positives.

### Allowlist
`gate_allow.txt` holds one regex per line, matched with `re.search` against `"{path}\t{stripped_line}"`.
- An optional `RULE_ID:` prefix scopes an entry to one rule.
- Blank lines and lines starting with `#` are ignored. By convention each entry has a `#` reason line above it, but the gate doesn't enforce that.
- An allowlisted hit is counted, not printed.
- An invalid regex is a config error: exit 2 and name the line.

### Config file (`gate_config.json`)
```json
{
  "skip_globs": ["**/test_*.py", "**/*_test.py", "**/conftest.py", "**/*.test.ts", "**/__tests__/**", "app/web_ui/src/lib/api_schema.d.ts", "..."],
  "checks": {
    "history-comment": {"enabled": true, "severity": "FAIL", "paths": [], "exclude": []},
    "...": {}
  },
  "env_access_allowed": ["libs/core/kiln_ai/utils/config.py", "..."],
  "module_level_call_ignore": ["\\.include_router\\(", "..."],
  "module_level_construct_patterns": ["\\bSettings\\(", "..."]
}
```
- A check missing from `checks` is disabled.
- An unknown check id is a config error (exit 2).
- The Kiln and kiln_server configs differ only in data.

Kiln `env_access_allowed` starts with:
- `libs/core/kiln_ai/utils/config.py`
- `app/desktop/desktop.py`
- `app/desktop/dev_server.py`
- `app/desktop/dev_app.py`
- `app/desktop/dev_env.py`
- `.agents/**`

The coding agent adjusts it to the real config modules and entry points it finds; existing calls elsewhere are grandfathered by the diff anyway.

kiln_server `env_access_allowed` lists its config module and its entry points (API, job runner, CLIs, scripts); the list lives in the kiln_server repo.

### Code structure
- **Small pure functions:**
  - `parse_unified_diff(text) -> list[Line]`
  - `extract_comment(line, lang) -> str | None`
  - `run_checks(lines, cfg, allow) -> Result`
  - `format_result(result) -> str`
- `main(argv) -> int` is the only function that touches `sys.argv`, `subprocess` and the filesystem roots.
- No module-level mutable state. The patterns are module-level constants (tuples of compiled regexes). This is the script following its own rules.

## 3. Gate tests (`test_conventions_gate.py`)

pytest, stdlib plus pytest only. They are synced too, so they must not depend on either repo's files: they use a fixture config written to `tmp_path` and import the script by path (`importlib.util.spec_from_file_location`, relative to `__file__`).

- **Diff parsing:**
  - multi-hunk diffs with line numbers;
  - new files;
  - renames;
  - `\ No newline`;
  - deletions ignored.
- **Comment extraction:**
  - `#` inside strings;
  - URLs with `//`;
  - `/* */`;
  - JSDoc `*` lines;
  - `<!-- -->`.
- **Each check:** at least one hit and one non-hit. `history-comment` gets a parametrized table: every pattern hits, and the false-positive guards ("is used to", "now") don't.
- **Path scoping:** skip globs, `paths`/`exclude`, `env_access_allowed`.
- **Allowlist:**
  - scoped and unscoped entries;
  - comments and blanks;
  - an invalid regex exits 2.
- **End-to-end through `main()`:**
  - in a temporary `git init` repo (`subprocess`, `git -c user.email=… commit`), `--range`, `--worktree` (including an untracked file) and `--files`;
  - exit codes 0, 1 and 2;
  - the output format and summary line.

How to run the tests:
- **Kiln:** `uv run python -m pytest .agents/skills/kiln-conventions/scripts/test_conventions_gate.py`. pytest doesn't collect dot-directories when it runs from the repo root, so the default suite doesn't pick them up.
- **kiln_server:** the same command against its skill path.

`SKILL.md` has a short "Maintaining the gate" section with this command.

## 4. Skills

### `SKILL.md` (≤ ~120 lines)
- **Frontmatter:**
  - `name: kiln-conventions` (or `kiln-server-conventions`);
  - a `description` that triggers before writing or changing Python/TS/Svelte code in the repo, and when reviewing code.
- **Body:**
  1. Read `references/rules.md`.
  2. Read the area reference(s) from the path table.
  3. After writing code, run `uv run python .agents/skills/<skill>/scripts/conventions_gate.py --worktree` (or `--range origin/main...HEAD` for a branch). Fix every FAIL, or add an allowlist entry (with a reason line) only if the hit isn't a real violation; a FAIL that can't be fixed without an out-of-scope refactor (rule H23) is left in place and reported with the rule id, `path:line`, and the refactor it waits on. Name each WARN in the end-of-task summary with a one-line justification.
  4. Self-check the review-only rules.
- **Path → reference table.**
- Kiln: "UI changes also load `kiln-ui`".
- "Maintaining the gate": the test command, plus where the shared files live.
- kiln_server: "shared files are synced from Kiln, so edit them there and run `utils/sync_conventions.sh`".

### `rules.md`
- The rules from functional spec §4 A–H.
- Each rule: a one-line imperative, at most one line of why, and one ❌/✅ example (2–6 lines each) taken from or modelled on real code.
- Rules the gate enforces are tagged with their rule id, e.g. `(gate: history-comment)`.
- It contains no repo-specific paths, because it's shared. Where a rule needs specifics ("dependency direction of the area"), it points to the area reference.

### References
Each reference has three sections: Gotchas, Where things go, and Startup (runtime areas only).
- Facts point to symbols (module, class or function names), never line numbers.
- Each fact is checked against current `main` when it's written.
- Kiln content comes from `research/audit/*.md`, limited to the topics listed in functional spec §4. kiln_server content comes from the kiln_server audit reports, which live outside this repo; the manager passes their path to the phase 2 agent.
- No content about bugs that have open fix PRs. Revisit those once the PRs merge.

## 5. Calibration (part of phase 1)

Before finishing, the coding agent:
1. Runs `--files` over the main source roots of Kiln: `libs/core/kiln_ai`, `libs/server/kiln_server`, `app/desktop`, `app/web_ui/src`.
2. Counts hits per rule.
3. Reviews a sample of `history-comment` hits, and removes or tightens any pattern whose sampled hits are mostly false positives.
4. Reports the final per-rule counts and the pattern changes in its return summary, and saves the `history-comment` hit list to `specs/projects/code_conventions/research/history_comment_baseline.txt`. That list is the work list for the comment-sweep phase.

`--files` runs are expected to hit existing code; only range and worktree runs gate.

## 6. Known limitations (documented in `SKILL.md` "Maintaining the gate")
- Python docstrings aren't scanned for history phrases.
- Multi-line `/* */` blocks are scanned only on their first line and on lines that start with `*`.
- `module-level-*` checks are heuristics, so they're WARN.
- Module-level calls written as assignments are only caught when the RHS matches the construct patterns.

## 7. Sync (`kiln_server/utils/sync_conventions.sh`)
```
utils/sync_conventions.sh [--check] [KILN_DIR]    # KILN_DIR defaults to ../Kiln
```
- **Shared files:**
  - `references/rules.md`
  - `scripts/conventions_gate.py`
  - `scripts/test_conventions_gate.py`
- **Source:** `$KILN_DIR/.agents/skills/kiln-conventions/`. **Destination:** `.agents/skills/kiln-server-conventions/`.
- **Header** (prepended on copy). It records `git -C $KILN_DIR rev-parse --short HEAD`.
  - Markdown: `<!-- Synced from Kiln-AI/Kiln .agents/skills/kiln-conventions/<file> @ <sha>. Edit it in Kiln, then run utils/sync_conventions.sh. -->`
  - Python: the same text as `# ` comment lines.
- **`--check`:**
  - Strips the header (the first line for md; the leading `# Synced from` comment lines for py) and diffs against the source.
  - Exits 1 and lists the files that differ.
  - Doesn't write anything.
- **Behaviour:** bash, `set -euo pipefail`. It fails clearly if `KILN_DIR` doesn't contain the source dir.

## 8. Wiring

**Kiln `AGENTS.md`:**
- Under "Agent Prompts", add: "Before writing or changing code, invoke the `kiln-conventions` skill (`.agents/skills/kiln-conventions/SKILL.md`)."
- In "General Agent Guidance", replace the long comment bullet with one line pointing to `rules.md` §A. The bullet's content moves into rules.md and isn't lost.

**Kiln `.agents/code_review_guidelines.md`:**
- Add near the top: "Apply `.agents/skills/kiln-conventions/references/rules.md` and the area references for the changed paths. Run the gate with `--range` on the PR's commits and report its FAIL and WARN hits."
- Remove the "Code Comments" sub-bullets on unnecessary and diff-dependent comments, and the "Editing globals" bullet; they are now in rules.md. Keep "Missing comments" (the why), the other guideline content, and everything SDK- or UI-specific.

**Kiln `kiln-ui` `SKILL.md`:** one line: "For code structure (stores, API calls, module layout), also follow `kiln-conventions` → `references/web_ui.md`."

**Kiln setup:** `.agents/claude/setup.sh` already copies `.agents/skills`, so nothing changes. Regenerate the local `CLAUDE.md` by running it; `CLAUDE.md` isn't tracked.

**kiln_server `AGENTS.md`:**
- The same "invoke `kiln-server-conventions`" line.
- Fix "`/agents` directory" to "`.agents` directory".
- The same comment-bullet replacement.

**kiln_server `.agents/code_review_guidelines.md`:** the same edits as Kiln.

**kiln_server `utils/setup_claude.sh`:** copy `.agents/skills` into `.claude/skills` (rm then copy, as in Kiln's script), instead of `.cursor/skills`.

## 9. Error handling
- **Gate:**
  - git failures (bad range, not a repo) print git's stderr and exit 2;
  - unreadable files are skipped;
  - config errors exit 2 with the key or line.
- **Sync script:** fail fast with a message. It never half-writes a file: it writes to a temp file, then moves it into place.

## 10. Testing strategy
- The gate gets unit and end-to-end tests (§3). They run in both repos with the command in `SKILL.md`.
- The skills and references are prose. The coding agent checks every symbol a reference names with `git grep` (it must exist on the current branch) and every relative link.
- The sync script gets a manual run in phase 2: sync, then `--check` → 0; edit a copy, then `--check` → 1. These are recorded in the return summary. No automated test, because bash plus two checkouts isn't worth a harness.
