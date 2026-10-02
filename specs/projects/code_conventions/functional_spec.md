---
status: complete
---

# Functional Spec: Code Conventions Skills

## 1. Purpose

Coding agents working in Kiln and kiln_server keep producing the same problems: comments that narrate history, module-level state, modules that set themselves up on import, startup code spread across many places, and code that reads config from a global deep inside the call stack. The [audit](research/audit/README.md) shows these patterns are already widespread, so agents copying nearby code spread them further.

This project gives agents, human authors and reviewers three things:

1. **One set of rules** for how code is written in both repos.
2. **Per-area gotchas.** These are facts about the current code that are easy to get wrong, such as "settings.yaml wins over env vars" or "`built_in_models` is swapped by a background thread".
3. **A cheap mechanical check** on changed lines, so the most greppable rules get enforced rather than just requested.

Existing code is grandfathered. The rules apply to code that a change adds or modifies. Refactors to bring old code in line are separate projects.

## 2. Deliverables

| # | Deliverable | Repo |
|---|---|---|
| D1 | `kiln-conventions` skill | Kiln |
| D2 | `kiln-server-conventions` skill | kiln_server |
| D3 | Shared universal rules, with one canonical copy in Kiln and a synced copy in kiln_server | both |
| D4 | Conventions gate: a diff-based checker script, shared between the repos | both |
| D5 | Wiring: `AGENTS.md`, code review guidelines, setup scripts, and a pointer from `kiln-ui` | both |
| D6 | Comment sweep: fix the comment violations found in the audit | both |

Each repo gets its own PR(s). Kiln is public and kiln_server is private, so nothing kiln_server-specific (architecture details, security-relevant gotchas) goes into the Kiln repo. kiln_server's gotchas live only in kiln_server.

## 3. The skills (D1, D2)

### 3.1 When an agent uses it

`AGENTS.md` in each repo tells agents to invoke the conventions skill **before writing or changing code**, and code reviewers to apply it **when reviewing**. That covers Python and TS/Svelte. Docs-only and spec-only changes don't need it.

The skill must work for an agent with no context on the repo, and it must be cheap to load:

- `SKILL.md` stays short, ≤ ~120 lines. It says what to read, in what order, and the end-of-task step.
- The universal rules live in one file, `rules.md`, that the agent always reads.
- Per-area references are read **only for the areas the change touches**. The agent works out the areas from the paths it's editing, using a path → reference table in `SKILL.md`.

### 3.2 Flow

1. Read `rules.md`.
2. Read the area reference(s) for the paths being changed.
3. Write the code.
4. Before finishing, run the conventions gate on the change (§5). Fix every FAIL, or allowlist it only if the hit isn't a real violation; a FAIL that can't be fixed without an out-of-scope refactor (rule H24) is left in place and reported with the rule id, `path:line`, and the refactor it waits on. Name each WARN in the end-of-task summary with a one-line justification, or fix it.
5. Self-check the rules the gate can't catch (§4, marked *review-only*).

### 3.3 Layout

```
Kiln/.agents/skills/kiln-conventions/
  SKILL.md
  references/
    rules.md               # canonical universal rules (D3)
    core.md                # libs/core
    server_desktop.md      # libs/server + app/desktop
    web_ui.md              # app/web_ui
  scripts/
    conventions_gate.*     # canonical gate (D4)
    gate_config.*          # Kiln-specific path settings for the gate, not synced
    gate_allow.txt         # Kiln allowlist, not synced

kiln_server/.agents/skills/kiln-server-conventions/
  SKILL.md
  references/
    rules.md               # synced copy, with a "do not edit here" header
    api.md                 # the API service
    jobs_pipelines.md      # jobs, pipelines and optimizers
  scripts/
    conventions_gate.*     # synced copy
    gate_config.*          # kiln_server-specific
    gate_allow.txt
```

Each reference has three sections:

- **Gotchas**: facts about the current code that are easy to get wrong, each with a pointer to a symbol (not a line number, because those rot).
- **Where things go**: which module owns what, and where a new route, service, store, job or provider goes.
- **Startup**: for runtime areas, the list of entry points and what each one sets up.

### 3.4 Web UI and `kiln-ui`

`kiln-ui` covers visual design and house controls. This project covers code structure. They stay separate:

- `web_ui.md` lives in the conventions skill.
- `kiln-ui` gets one line pointing to it.
- The conventions skill's `SKILL.md` says that UI changes also need `kiln-ui`.

## 4. Rule content

These are the rules `rules.md` must carry, in short imperative form. Each rule gets one ❌/✅ example, taken from real code where possible. Rules marked *(gate)* are checked by D4; the rest are *review-only*.

### A. Comments
1. A comment must make sense to someone who never saw the diff. Don't narrate history or change: "no longer", "used to", "previously", "switched to", "bumped from", "vestigial", "after the refactor". Don't reference planning docs: "Phase N", "functional spec §x", "(P2)". History goes in the commit message or PR description. *(gate)*
2. Don't write comments that restate the code, or docstrings that only restate the name. Public SDK docstrings and published API route docstrings are the exception: they're docs for external readers, so write them well.
3. Comments explain a non-obvious *why*, in 1–3 lines. If a guard needs a paragraph, it needs a better name or a helper.

### B. Startup and entry points
4. Each runtime has one composition root. A process (app, server, worker, CLI, script) starts by calling one bootstrap function. That function owns process-wide setup: logging, error reporting, certs, library config, model list.
5. Modules do no work at import time: no I/O, no network, no env or config reads, no threads, no client creation, no registration, and no changes to stdlib or third-party globals. Module top level only defines things. *(gate: bare calls at module level, WARN)*
6. App factories are pure. Long-lived resources are created at startup (FastAPI `lifespan`) and held by the app (`app.state`), not by modules.

### C. State and globals
7. No new module-level mutable state: no `global` *(gate)*, no module-level dict, list or set that gets mutated, no ClassVar registries. App-scoped objects are created at startup and passed in or injected.
8. If a test has to reset it or patch it, it's in the wrong place. Don't add `reset()` hooks to production code for tests.
9. No `asyncio.Lock`, `Semaphore` or `Event` in a module or process singleton.
10. A cache needs an owner, a bound, and an invalidation path. Never keep permission or trust decisions in a global.

### D. Config
11. Read config once at the edge (entry point, route handler or dependency) and pass values down. Don't read the global config deep in the call stack.
12. Parse config values with real parsers. Never use `bool(str)`. *(gate: `bool(os.environ…)` / `bool(os.getenv…)`)*
13. Read env vars only in the config module and the entry points. Never configure a library by writing `os.environ`. *(gate: env access outside allowed paths)*
14. Pydantic `default_factory` and validators are pure: no config, env, filesystem or network.
15. Config picks the implementation. Code reads the setting and builds what it names; it doesn't branch on the environment name to pick, require or forbid an implementation, and doesn't add startup guards that override the deploy config.

### E. Modules and layering
16. Thin edges. Route handlers and pages parse input, call one service or flow function, and map the result. Multi-step logic goes in a service module (Python) or a `.ts` module (web) with unit tests. As a guide, a handler over ~50 lines or one calling several services/endpoints should be split. That number is a prompt to stop and think, not a hard limit.
17. Service and util code doesn't import router modules and doesn't raise HTTP exceptions. Routers don't import each other or each other's `_private` names.
18. Respect the dependency direction of the area. Each area reference states it. *(gate where it's a path rule, e.g. web `lib/` must not import `routes/`)*
19. No catch-all modules. Put a function in the module of the domain it belongs to.
20. Test helpers live in test files or test-support modules, never in production packages.
21. Prefer one shared helper or table-driven spec over near-copies. A "keep in sync" comment means the code should be extracted.

### F. Library vs. application
22. Library code doesn't change the global state of the process hosting it: litellm settings, logging handlers or levels, `csv`, `mimetypes`, `os.environ`, `sys.modules`, `atexit`, signal handlers. If host-level setup is needed, the library exposes a `setup_*()` that adds to existing state rather than replacing it, and the entry point calls it.

### G. Async and I/O
23. No blocking I/O inside `async def`. Every outbound call has a timeout. Create clients once per process, not per call.

### H. Grandfathering
24. New code follows these rules even when the code around it doesn't. Don't copy a pattern from nearby code that breaks a rule. Don't rewrite neighbouring code to comply either, unless the change is already touching it. If a rule can't be followed without a refactor, follow the local pattern and say so in the end-of-task summary.

### Kiln area gotchas (public; for `references/*.md`)

The Kiln references must cover at least these topics. Facts come from the audit; check them against the code when writing.

- **core**
  - `Config` precedence: the in-memory value, then settings.yaml, then the env var, then the default. A saved value can't be overridden by env. This is documented, and stays as it is.
  - `Config` reads the file once and caches it for the whole process.
  - The root `conftest.py` resets the singleton.
  - `built_in_models` is replaced by a background refresh, so treat it as read-only and don't keep references to slices of it.
  - The `ModelName` enum vs. names that arrive through the remote model list.
  - Adapters are the hot path: no blocking I/O and no per-call file reads.
  - `utils/` must not import `adapters/`, `tools/` or `datamodel/`.
  - Datamodel validators are pure.
  - The checklist of places to change when adding a provider.
  - The SDK must not mutate host globals.
- **server_desktop**
  - The list of entry points and what each one sets up.
  - Where new startup work goes (lifespan), not `make_app()` or import time.
  - Importing `kiln_server.server` currently builds an app.
  - Use the existing job registry for background work; don't add new dict-based job stores.
  - Shared logic goes in a services module, not imported from another router.
  - Read-modify-write of `Config` lists and dicts isn't atomic.
  - No `requests` inside async handlers.
  - `libs/server` must not know about desktop features.
- **web_ui**
  - Use the typed API client and the shared error helper.
  - Stores don't set themselves up on import.
  - `indexedDBStore` / `localStorageStore` are never created inside functions.
  - Lookup functions don't trigger loads.
  - Load-once caches can retry and reset; there's one place that invalidates model caches.
  - `lib/` doesn't import `routes/`.
  - Page logic goes into `.ts` flow modules.
  - Errors are shown in the page, never with `alert()`.

### kiln_server area gotchas (private; written in the kiln_server repo only)

These cover:

- How `Settings` is loaded and when.
- How kiln_ai is configured from kiln_server, and the rule that kiln_ai's `Config` is single-user and never holds tenant data.
- Never mutating kiln_ai globals in a request.
- Multi-tenant state rules.
- The entry points (API, job runner, optimizer CLI, scripts) and their startup.
- Package dependency direction.
- The one singleton pattern to use.
- Logging.
- Handler thinness.
- Job-route invariants: ownership check, and usage is recorded *before* dispatch on purpose (jobs are expensive, so the route errs on the restrictive side).

Where a gotcha describes a bug that's being fixed in a separate PR, the reference describes the behaviour after the fix if that PR has merged by the time the reference is written. Otherwise it describes the current trap and gets updated when the fix lands.

## 5. Conventions gate (D4)

### 5.1 Behaviour
- **Input modes**, the same as `kiln-ui`'s `ui_gate.sh`:
  - `--range <git-range>`: added lines of a commit range, for a branch or PR.
  - `--worktree`: added lines of uncommitted changes, plus untracked files read whole.
  - `--files <paths…>`: whole files, used for audits and for the comment sweep.
- **Only added lines are checked** in range and worktree modes. That's how existing code is grandfathered.
- **Skipped:** test files (`test_*.py`, `*_test.py`, `conftest.py`, `*.test.ts`, `__tests__/`), generated files (e.g. `api_schema.d.ts`, codegen output), and non-code files.
- **Output:** one line per hit, `SEV<TAB>RULE<TAB>file:line<TAB>snippet`, then a summary count. Exit code 1 if any FAIL remains, 0 otherwise. Bad usage exits 2.
- **Severities:**
  - FAIL means fix it, or add an allowlist entry with a reason only if the hit isn't a real violation; a FAIL that can't be fixed without an out-of-scope refactor (rule H24) is left in place and reported with the rule id, `path:line`, and the refactor it waits on.
  - WARN means justify it in the end-of-task summary.
- **Allowlist:** `gate_allow.txt` holds one regex per line, matched against `file<TAB>snippet`, optionally scoped with a `RULE:` prefix. Every entry has a `#` reason comment on the line above it. There is no inline pragma, so allowances stay visible in one file.

### 5.2 Checks

| Rule id | Sev | Applies to | Flags (on added lines) |
|---|---|---|---|
| `history-comment` | FAIL | py, ts, svelte | Comment text with history or planning phrases (a curated phrase list, tuned on the audit's examples so the false-positive rate stays near zero; bare "now" isn't in the list) |
| `global-stmt` | FAIL | py | A `global` statement |
| `bool-env` | FAIL | py | `bool(os.environ…)` / `bool(os.getenv…)` |
| `env-access` | FAIL | py | `os.getenv`, `os.environ[...]`, `os.environ.get` outside the repo's allowed paths (config module(s), entry points), set in `gate_config` |
| `core-config-shared` | FAIL | Kiln `libs/core` only | New `Config.shared()` in `libs/core/kiln_ai/` |
| `lib-imports-routes` | FAIL | Kiln web | A `lib/` file importing from `routes/` |
| `module-level-call` | WARN | py | A bare call statement at column 0 (e.g. `setup_x()`, `mimetypes.add_type(...)`), excluding `if __name__ == "__main__":` blocks |
| `module-level-subscribe` | WARN | Kiln web `.ts` | `.subscribe(` at column 0 in a `lib/` module |

Repo-specific path settings (which checks apply where, allowed env-access paths) live in `gate_config`, which is not synced. The gate script itself is identical in both repos.

### 5.3 Cost bound

The gate must stay cheap:

- It uses standard tools only (bash plus grep/awk, or stdlib Python). No new dependencies.
- It runs on a typical PR diff in under 2 seconds.
- It is *not* added to CI or `checks.sh` in this project (see §8, Q1).

## 6. Sync of shared files (D3)

- Canonical files: `references/rules.md` and the gate script in `scripts/`, under `Kiln/.agents/skills/kiln-conventions/`.
- kiln_server has a sync script, `utils/sync_conventions.sh [path-to-Kiln-checkout]`, defaulting to `../Kiln`:
  - It copies both files into `.agents/skills/kiln-server-conventions/`.
  - It prepends or keeps a header saying the file is synced from Kiln and must be edited there.
  - It records the Kiln commit it synced from.
  - `--check` exits 1 if the copies differ from the given Kiln checkout. It is manual, not CI.
- Edits to the shared rules happen in Kiln first, then get synced in a kiln_server PR.

## 7. Wiring (D5) and comment sweep (D6)

### Wiring
- **Kiln `AGENTS.md`:** under "Agent Prompts", invoke `kiln-conventions` before writing or changing code. Point the existing comment bullet in "General Agent Guidance" to the rules instead of repeating them. Regenerate `CLAUDE.md` with `.agents/claude/setup.sh`.
- **Kiln `.agents/code_review_guidelines.md`:** apply `rules.md` and the relevant area references, and run the gate with `--range` on the PR. Replace the comment and globals bullets that the rules now cover with a pointer, so the same rule doesn't live in two places.
- **kiln_server `AGENTS.md` and `.agents/code_review_guidelines.md`:** the same changes, plus fixing the stale `/agents` path (it's `.agents`).
- **kiln_server `utils/setup_claude.sh`:** copy `.agents/skills` into `.claude/skills`, as Kiln's setup does. It currently copies `.cursor/skills`.
- **`kiln-ui` `SKILL.md`:** one line pointing to `kiln-conventions` for code structure.
- **Outside the repos:** the workspace `CLAUDE.md` copy step needs to include kiln_server's skill too. This is a manual note for the user; it's not part of either repo.

### Comment sweep
- Run the gate with `--files` over each repo, plus the audit's lists of zigzag, spec-reference and restating comments. Fix each hit: rewrite it as a short "why", or delete it. These PRs change comments only, no code.
- The goal is that after the sweep, `history-comment` reports zero hits across the codebase. Then grandfathering isn't needed for that rule, and false positives are easy to spot.
- Restating comments can't be gated, so only the audit's listed examples and anything obvious in the same files get cleaned. This is not a line-by-line review of the whole codebase.

## 8. Out of scope

- The refactors in the audit's backlog (composition roots, Config injection, singletons into app scope, god-file splits, the store foundation, layering). Each becomes its own spec project, written against these rules.
- Changing `Config` precedence or any runtime behaviour.
- The small bugs from the audit. These are being fixed in separate PRs.
- CI enforcement of the gate (see Q1).
- Lint-tool changes (ruff banned-api, ESLint `no-restricted-imports`, import-linter). The diff gate covers the same rules more cheaply while the old code is grandfathered.

## 9. Resolved questions

1. **Gate in CI:** no, not for now. Agents and reviewers run it. Revisit once it has run for a while without false positives.
2. **Skill names:** `kiln-conventions` (Kiln) and `kiln-server-conventions` (kiln_server).
3. **Rule list:** as written in §4.
