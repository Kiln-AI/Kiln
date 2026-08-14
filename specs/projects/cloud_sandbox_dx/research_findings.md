---
status: complete
---

# Research Findings: Kiln in Claude Code Cloud Sandboxes

All numbers measured on a live cloud sandbox, 2026-08-14, branch
`claude/kiln-sandbox-perf-qisyeg` (base: `main` @ 7b70de1).

Sandbox spec: **4 vCPU, 15 GB RAM, 252 GB disk**. Toolchain as shipped:
`uv 0.8.17`, `node 22.22.2`, `npm 10.9.7`, system python `3.11.15`
(3.12.3 and 3.13.12 also present, none with tkinter).

---

## 1. What the sandbox actually gives you at session start

| Thing | State |
|---|---|
| `.venv` | **absent** |
| `app/web_ui/node_modules` | **absent** |
| `/root/.cache/uv` | present, 224 MB, warm for the current lock |
| `/root/.npm` | present, 127 MB, warm |
| `CLAUDE.md` | **absent** (gitignored) |
| `.claude/skills/` | **absent** (gitignored) |
| `.mcp.json` / HooksMCP server | **absent** (gitignored) |
| `misspell` | not installed |

The repo already ships `.agents/claude/setup.sh`, which creates the last three
(copies `AGENTS.md` → `CLAUDE.md`, copies `.agents/skills` → `.claude/skills`,
copies `.agents/mcp.json` → `.mcp.json`). **Nothing in the sandbox runs it.**

Consequence: an agent starts with no project instructions, no repo skills, and
no HooksMCP. `AGENTS.md` tells agents to fetch guidance via a `get_prompt` tool
that does not exist in this environment, and lists check commands that are only
reachable through the missing MCP server.

`.config/utils/setup_env.sh` cannot fill the gap either — it is interactive
(`read -rp "Install Kiln workspaces?"`) and would hang unattended.

---

## 2. Setup speed — measured, and **not** worth optimizing

| Step | Warm cache | Cold cache (caches wiped) |
|---|---|---|
| `uv sync --frozen --all-packages` | 11.6 s | **11.6 s** |
| `npm ci` (601 MB of node_modules) | 27.3 s | **25.6 s** |
| `uv python install 3.13` | — | 2.2 s |
| **Total** | **~39 s** | **~37 s** |

Cold cache was produced by `uv cache clean` (removed 84,520 files / 4.5 GiB) and
`npm cache clean --force`, then re-running both installs.

**Conclusion: there is nothing to win here.** Cold and warm are within noise of
each other, because PyPI and the npm registry are in the sandbox's `no_proxy`
list and download at effectively local speed; the bottleneck is disk write and
linking, not network. An R2/S3 dependency cache would add complexity and save
approximately zero seconds. Setup is already ~37 s and is not the problem.

---

## 3. The real problem: the sandbox ships a `uv` too old for this repo

`pyproject.toml:32` sets `exclude-newer = "7 days"` — uv's *relative span* syntax.

| uv version | parses `"7 days"`? |
|---|---|
| 0.8.17 (**shipped in sandbox**) | ✗ `TOML parse error … failed to parse year in date "7 days"` |
| 0.9.0 / 0.9.3 / 0.9.6 / 0.9.9 | ✗ |
| **0.10.0** | ✓ |
| 0.12.5 (current) | ✓ |

When uv can't parse the setting it silently ignores it and **re-resolves the
whole dependency graph from scratch**. Measured effect of one plain
`uv run python -c "print('hello')"`:

| uv version | wall time | `uv.lock` diff | packages touched |
|---|---|---|---|
| **0.8.17** | **16.4 s** | **+3534 / −2284 lines** | uninstalled 126, installed 132 |
| **0.12.5** | **0.27 s** | none | none |

The re-resolve pulls fastapi 0.141.1 against starlette 1.6.0, which breaks
imports repo-wide:

```
ImportError: cannot import name 'collapse_excgroups' from 'starlette._utils'
```

That takes the suite from 5 collection errors to **14**. Repairing it costs one
`uv sync --frozen --all-packages` (0.56 s) — but only if you know to run it.

This is not a repo bug and it is not fixable by editing call sites. **Plain,
non-frozen `uv run` is the documented interface everywhere**: `checks.sh`
(ruff / ruff format / ty), the `Makefile`, every action in
`.config/hooks_mcp.yaml`, `app/web_ui/src/lib/openapi_schema.sh`, every command
in `AGENTS.md`, and every `.agents/skills/*` script.

Worse: `checks.sh` starts the OpenAPI schema check **concurrently with** the
python test suite, and that schema check shells out to a non-frozen `uv run`.
On uv 0.8.17 that swaps 126 packages out from under a running pytest.

Also noted: the image sets `UV_NATIVE_TLS=true`, which modern uv warns is
deprecated in favour of `UV_SYSTEM_CERTS`. Pure noise on every invocation.

---

## 4. tkinter — and a fix that costs 2.2 seconds

No tkinter anywhere: not in the venv, not in any system python, no `python3-tk`.

Repo import sites:

| File | Usage | Needed headless? |
|---|---|---|
| `app/desktop/desktop_server.py:7` | only type annotations, lines 129 & 165 | no |
| `app/desktop/studio_server/import_api.py:2-3` | `tk` in an annotation; `filedialog` only inside `_show_file_dialog()` | no |
| `app/desktop/desktop.py:11` | real pyinstaller entry point | yes, legitimately |

Blast radius: 5 test modules cannot be collected —
`app/desktop/git_sync/test_sse_invariants.py`,
`app/desktop/studio_server/test_import_api.py`,
`app/desktop/studio_server/test_server.py`,
`app/desktop/test_desktop.py`,
`app/desktop/test_start_background_syncs.py` — and both
`check_schema.sh` and `generate_schema.sh` fail outright, since both import
`app.desktop.desktop_server`.

**The cheap fix:** CI already runs `uv python install 3.13`, and uv-managed
CPython builds bundle Tk. Verified in the sandbox:

```
uv python install 3.13          → 2.2 s, tkinter OK (Tk 8.6)
uv sync --frozen --all-packages --python 3.13  → 5.7 s
```

Results after switching the venv to uv-managed Python 3.13:

| | system py3.11 | uv-managed py3.13 |
|---|---|---|
| collection errors | 5 | **0** |
| tests collected | 16,337 | **16,389** |
| full suite | 6317 passed, 5 errors | **6369 passed, 0 errors**, 61.5 s |
| `check_schema.sh` | ImportError | **"OpenAPI schema up to date"**, 31.7 s |
| `uv run ./checks.sh --agent-mode` | cannot pass | **fully green, 2 m 23 s** |

3.13 is also what CI and the desktop app target, so this *reduces* environment
drift rather than adding a sandbox-only special case.

A repo-side lazy/`TYPE_CHECKING` import in `desktop_server.py` and
`import_api.py` is still worth doing independently — it helps every headless
Linux contributor, not just this sandbox — but it is no longer load-bearing.

---

## 5. Test performance

Python suite, on 4 vCPU:

| Config | Wall | CPU |
|---|---|---|
| `-n auto` (= 4 workers) | 62.6 s | 3 m 08 s |
| `-n 4` | 56.3 s | 3 m 03 s |
| `-n 8` | **89.1 s** (42 % worse) | 4 m 41 s |

- Parallel efficiency is **~3.0× on 4 cores**. That is healthy; `-n auto` is the
  right setting and oversubscribing actively hurts. **No change recommended.**
- 16,389 tests collected, **10,020 of them skipped** — nearly all
  `need --runpaid option to run`, parametrized across the model list (one test
  carries 566 params). They cost collection time on every run.
- Collection: **35 s cold**, 11.9 s warm (`__pycache__` + page cache).
- `import litellm` = **4.0 s**, paid once per pytest process (`conftest.py:7`)
  and therefore once per xdist worker.
- Fixed cost of a targeted run: **6.1 s wall to run 0.14 s of tests.** This is
  the tax an agent pays on every iterate-on-one-file cycle.
- `pytest --collect-only` **aborts** on collection errors
  (`Interrupted: 5 errors during collection`); the xdist run does not.

Web UI (`app/web_ui`), each measured separately:

| Command | Time | Result |
|---|---|---|
| `npm run format_check` | 16.3 s | clean |
| `npm run lint` | 15.5 s | clean |
| `npm run check` | 29.3 s | 0 errors, **4** warnings in 3 files |
| `npm run build` | 54.4 s | clean |
| `npm run test_run` | 27.6 s | 1163 passed |

Full `uv run ./checks.sh --agent-mode`: **2 m 23 s**, exit 0, working tree clean
— once uv ≥ 0.10 and Python 3.13 are in place.

---

## 6. Baseline noise on `main` (contradicting the earlier field notes)

The prior agent's report described a noisy baseline. Re-measured on `main`:

| Check | Their report | Measured on `main` |
|---|---|---|
| `npm run check` | 39 warnings / 18 files | **4 warnings / 3 files** |
| `ty check` | 2 errors in `g_eval.py` | **All checks passed!** |
| `pytest -n auto .` | 5 tkinter errors | 5 tkinter errors ✓ (0 on py3.13) |

Their first two numbers were branch-local, not baseline. Their §8 diagnosis that
"a merge broke the lockfile" was also a misattribution — that `collapse_excgroups`
ImportError is the uv-0.8.17 re-resolve, reproducible on a clean tree.

The tkinter-stub package they built is unnecessary given §4.

---

## 7. Answers to the questions that prompted this

- **Can setup be faster? Is a dependency cache worth it?** No. 37 s cold vs 39 s
  warm — the cache is already irrelevant. Don't build one.
- **Are other startup steps costing us?** Yes, but not in seconds: the *missing*
  setup step (`.agents/claude/setup.sh` never runs) costs correctness, not time.
- **Is tkinter blocking things?** Yes — 5 test modules and both schema scripts.
  Fixed by a 2.2 s Python install.
- **Are tests fast enough? Getting parallel perf?** Yes and yes. 3.0× on 4 cores,
  `-n auto` optimal. The addressable waste is the ~6 s fixed startup per
  invocation and ~10 k collected-then-skipped paid tests, not the runner config.
- **Anything else?** The uv version mismatch (§3) dwarfs everything else, and no
  amount of documentation fixes it — every documented command triggers it.
