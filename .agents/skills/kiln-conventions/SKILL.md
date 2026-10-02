---
name: kiln-conventions
description: Kiln's code conventions and per-area gotchas, plus a diff gate that enforces the mechanical ones. Invoke before writing or changing any Python, TypeScript or Svelte code in the Kiln repo (libs/core, libs/server, app/desktop, app/web_ui), and when reviewing such a change. Covers comments, startup and entry points, globals and module state, config reads, module layering, library-vs-app rules and async I/O.
allowed-tools: Read Grep Glob Bash
---

# kiln-conventions

One set of rules for how code is written in Kiln, the facts about the current code that are easy to get wrong, and a cheap check on the lines you add. Existing code is grandfathered: the rules apply to what your change adds or modifies.

Docs-only and spec-only changes don't need this skill.

## 1. Read the rules

Read `references/rules.md` in full. It is short, and every rule has a ❌/✅ example.

## 2. Read the reference for each area you touch

Pick the references from the paths you are editing. Read only those.

| Paths | Reference |
|---|---|
| `libs/core/**` | `references/core.md` |
| `libs/server/**`, `app/desktop/**` | `references/server_desktop.md` |
| `app/web_ui/**` | `references/web_ui.md` |

UI changes (anything under `app/web_ui` that renders) also need the `kiln-ui` skill (`.agents/skills/kiln-ui/SKILL.md`) for visual design and house controls. This skill covers code structure only.

## 3. Write the code

Follow the rules even where the surrounding code doesn't (rules.md H23). Don't copy a nearby pattern that breaks a rule, and don't rewrite neighbouring code to comply unless your change already touches it.

## 4. Run the gate on your change

From the repo root:

```
uv run python .agents/skills/kiln-conventions/scripts/conventions_gate.py --worktree               # uncommitted changes + untracked files
uv run python .agents/skills/kiln-conventions/scripts/conventions_gate.py --range origin/main...HEAD  # a branch or PR
uv run python .agents/skills/kiln-conventions/scripts/conventions_gate.py --files <path>...          # whole files or directories (audits)
```

It prints one line per hit, `SEV<TAB>RULE<TAB>path:line<TAB>snippet`, then a summary. Exit 1 means at least one FAIL.

- **FAIL**: fix it. If the hit is not a violation, add an entry to `scripts/gate_allow.txt` with a `#` reason line above it. Don't allowlist a real violation.
- **FAIL you can't fix without an out-of-scope refactor** (rules.md H23): leave it, and don't allowlist it. List it in your end-of-task summary and the PR description with the rule id, `path:line`, and the refactor it waits on. The gate isn't in CI, so a FAIL reported this way blocks nothing.
- **WARN**: fix it, or name it in your end-of-task summary with a one-line justification (for example "module-level-call `app.command(...)(...)` in `cli/cli.py`: Typer command registration at the CLI's composition root").

Only added lines are checked in `--worktree` and `--range` mode, so a hit is always on a line you wrote. `--files` reports existing code too; it's for audits, not for gating.

## 5. Self-check what the gate can't see

The gate catches history comments, `global`, `bool(os.getenv…)`, env reads outside the allowed paths, new `Config.shared()` in `libs/core`, `lib/` → `routes/` imports, and module-level calls, constructions and subscriptions. Before you finish, check the review-only rules yourself against your diff:

- A2/A3: no comment restates the code; each remaining comment is a 1–3 line *why*.
- B4/B6: startup work is in the entry point or `lifespan`, not in an app factory or a module.
- C7: no new module-level dict, list or set that gets mutated, and no ClassVar registries (the gate only catches `global`).
- C8–C10: no reset hooks for tests, no asyncio primitives in singletons, every cache has an owner, a bound and invalidation.
- D11/D14: config is read at the edge; validators and `default_factory` are pure.
- E15–E20: thin handlers and pages, no router-to-router imports, no `HTTPException` in services, no catch-all modules, no test helpers in production packages, no near-copies.
- F21: library code doesn't touch host-process globals.
- G22: no blocking I/O in `async def`; every outbound call has a timeout.

If a rule couldn't be followed without a refactor, say so in your summary (H23); for a gate FAIL, report it as in step 4.

## For reviewers

Apply `references/rules.md` and the area references for the changed paths. Run the gate with `--range <base>...<head>` on the PR and report every FAIL and every WARN that the author didn't justify. Accept a FAIL the author reported with its rule id, `path:line` and the refactor it waits on (rules.md H23); an allowlist entry for a real violation is a finding. Rule violations in added code are findings, not nits.

## Maintaining the gate

Files in this skill:

- `references/rules.md`, `scripts/conventions_gate.py` and `scripts/test_conventions_gate.py` are **shared**: kiln_server carries synced copies. Edit them here, in Kiln, then sync them into kiln_server with its `utils/sync_conventions.sh`.
- `scripts/gate_config.json` (skipped paths, which checks run where, allowed env-access paths, module-level patterns) and `scripts/gate_allow.txt` are Kiln-only. The gate reads both from its own directory.

Run the gate's tests (stdlib + pytest only; the default repo test run doesn't collect dot-directories):

```
uv run python -m pytest .agents/skills/kiln-conventions/scripts/test_conventions_gate.py
```

Config notes: a check missing from `checks` is disabled; an unknown check id or an invalid regex exits 2. Globs support `*` and `?` (within one path segment) and `**/` (zero or more directories); brackets are literal, so `routes/[project_id]/**` works. Allowlist lines are Python regexes searched in `path<TAB>stripped line`, optionally prefixed `rule-id:`.

Known limitations:

- Python docstrings aren't scanned for history phrases; only `#` comments are.
- Comment detection is per line. A multi-line `/* */` or `<!-- -->` block is scanned only on its first line and on lines that start with `*`.
- Quote tracking is per line too: an apostrophe earlier on the line (Svelte markup text like `<p>Don't</p> <!-- … -->`, or a `'` in a regex literal) hides a comment that follows it.
- The `module-level-*` checks are heuristics, which is why they are WARN. A module-level call written as an assignment is caught only when the right-hand side matches `module_level_construct_patterns`.
- The `history-comment` phrase list skips common runtime-state phrasings ("no longer matches", "previously selected"), so some history phrased that way slips through. Review still applies rules.md A1.
