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

---

# Round 2 — follow-up measurements

## 8. How to actually upgrade uv in the sandbox

`uv self update` **does not work here** and the failure is structural, not
transient (retried, same result):

```
error: GitHub API rate limit exceeded. Please provide a GitHub token via the `--token` option.
```

It resolves releases through the GitHub API, whose limit is per egress IP, and
sandboxes share one. `astral.sh` is also unreachable through the proxy.

PyPI works, and is the fix:

```
pip install --user --upgrade uv     → 2.4 s, installs uv 0.12.5
```

It writes to `/root/.local/bin/uv` — the same path as the pre-installed binary,
already first on `PATH` — so it is a clean in-place replacement.

Verified end-to-end afterwards:

| | uv 0.8.17 | after upgrade (0.12.5) |
|---|---|---|
| plain `uv run python -c "print(1)"` | 16.4 s | **0.072 s** |
| `uv.lock` afterwards | +3534 / −2284 lines | **untouched** |
| TOML parse error on every call | yes | gone |

**A 2.4 s pip install eliminates the entire top-priority problem.**

## 9. MCP: project `.mcp.json` is never auto-trusted

Tested directly in a cloud session with `claude mcp list`:

| Mechanism | Result |
|---|---|
| nothing (fresh state) | ⏸ Pending approval |
| `.claude/settings.local.json` → `enabledMcpjsonServers: ["HooksMCP"]` | ⏸ Pending |
| `~/.claude.json` → `projects[path].enabledMcpjsonServers` | ⏸ Pending |
| `~/.claude.json` → `projects[path].hasTrustDialogAccepted: true` | ✓ works |
| `.claude/settings.local.json` → `enableAllProjectMcpServers: true` | ⏸ Pending |
| **`~/.claude/settings.json` → `enableAllProjectMcpServers: true`** | **✓ Connected** |

Control: setting trust back to `false` returned it to Pending, confirming the
mechanism. **Project-scoped settings files do not work for this — only user-level
settings or the trust flag.** So this belongs in the cloud environment config,
not the repo.

Separately, `.agents/claude/setup.sh` was verified to work mid-session: after
running it, `CLAUDE.md` and all five repo skills became available without a
session restart. Only MCP needs the extra setting.

The server itself fails to start on `hooks-mcp 0.2.4` + `mcp 2.0.0`
(`'Server' object has no attribute 'list_tools'`). With a working server the full
chain reports **√ Connected**, so the path is proven; being fixed upstream in
hooks-mcp 0.2.5.

## 10. Pytest startup cost — the "E4" conftest change

The root `conftest.py` imported `litellm` at module scope. pytest imports the root
conftest on **every** invocation, so every run paid the litellm import even when no
test touched it. The change: drop the module-level import, have the autouse
`_clear_httpx_clients` fixture use `sys.modules.get("litellm")` and return early if
absent, fold the session-scoped `setup_test_logging` into that guarded path, and
move `KilnAttachmentModel` under `TYPE_CHECKING`.

Safe because: the cache flush is only skipped when nothing imported litellm (so
there are no cached clients to flush), and `setup_litellm_logging` is idempotent —
it early-returns if the callback is already installed (`logging.py:137-140`).

| | collect | full suite `-n auto` |
|---|---|---|
| baseline | 22.9 s (16,389 tests) | **63.3 s** — 6369 passed, 10020 skipped |
| **E4** | 22.4 s (16,389 tests) | **58.9 s** — 6369 passed, 10020 skipped |
| baseline + paid ignored | 21.2 s (6,203) | 55.7 s — 5952 passed |
| E4 + paid ignored | 20.5 s (6,203) | 47.6 s — 5952 passed |

Single test file (42 tests, 0.14 s of actual testing):

| baseline | E4 |
|---|---|
| 7.40 / 7.73 / 6.86 s | **0.96 / 0.91 / 2.03 s** |

**~7× on the inner loop**, and identical pass/skip counts on the full suite.

**Negative result — ignoring the paid-heavy files is not worth it.** The 8 files
holding ~9,734 of the ~10,020 paid tests can be `--ignore`d, cutting collection
from 16,389 to 6,203 tests, but that saves only **~1.7 s**. The cost is module
*imports*, not parametrize expansion. Not worth the risk of silently skipping
tests. Rejected.

## 11. Why `import litellm` costs ~4 s

It **does** make a network request at import: it fetches the model cost map from
`raw.githubusercontent.com`. In this sandbox the fetch succeeds and costs ~0.6 s —
it is not a hang.

`LITELLM_LOCAL_MODEL_COST_MAP=True` forces the bundled copy. Six alternating reps:

| | median |
|---|---|
| baseline | **3.86 s** |
| local cost map | **3.26 s** |

So the network fetch is only ~0.6 s of ~3.9 s. The remaining ~3.2 s is pure import
work — **2,148 modules**:

| package | self time | modules |
|---|---|---|
| litellm | 1.804 s | 822 |
| openai | 0.448 s | 609 |
| fastapi | 0.160 s | 35 |
| aiohttp | 0.109 s | 40 |

Worst single module: `litellm.proxy._types` at **0.431 s** — 4,834 lines of pydantic
models for litellm's *proxy server*, pulled in transitively by `secret_managers/*`
just for a couple of enums, dragging fastapi with it. Then
`litellm_core_utils/default_encoding` at 0.218 s (`tiktoken.get_encoding`). Not
eagerly imported: boto3, botocore, google.*, anthropic, transformers.

There is no setting that gets this meaningfully below ~3.2 s.

**Correctness risk if set globally:** the bundled map has **2,733 models vs 3,020
remote — 290 missing**, including `claude-opus-5` and `claude-sonnet-5`, and 30
shared models have different `input_cost_per_token`. Kiln reads the derived cost at
`litellm_adapter.py:787` (`response._hidden_params.get("response_cost")`), so
forcing the local map in production would silently yield `None` or stale costs for
the newest models. **Never set it in `pyproject.toml` or the app.**

Test-only is safe, and verified: the repo has **zero** call sites for
`litellm.model_cost`, `get_model_info`, or `completion_cost`; Kiln's own context
windows come from its hand-maintained `ml_model_list.py`. The justification for
setting it in the test environment is **hermeticity, not speed** — a suite that
makes an HTTP request to GitHub at import time is a latent flake, and with E4
landed the inner loop does not import litellm at all, so the 0.6 s only applies to
full-suite runs.

## 12. How cloud environment setup scripts actually run (round 3)

This was checked after planning, because the plan had assumed a setup script could
call a script inside the repo. It cannot, and the reasons change the design.

From the [cloud environments docs](https://code.claude.com/docs/en/cloud-environments#setup-scripts):

1. **It is not a per-session hook.** "The setup script runs the *first time* you
   start a session in an environment. After it completes, Anthropic snapshots the
   filesystem... New sessions start with your dependencies... and **skip the setup
   script step**." It re-runs only when the script or the network config changes,
   or after roughly seven days.
2. **A non-zero exit stops the session from starting.** "Exit zero: if the script
   exits non-zero, the session fails to start." This makes a plain `set -e` script
   with hard `exit 1` paths dangerous: one flaky `npm` fetch and the sandbox will
   not boot.
3. **Five minute budget**, with parallelism explicitly recommended.
4. **The docs route project setup elsewhere:** "Use a setup script to provision
   *the VM itself*... Use a SessionStart hook for project setup that should run
   everywhere, cloud and local, like `npm install`."

### The filesystem does persist — measured

A container restart mid-session preserved every gitignored artifact — `.venv`,
`app/web_ui/node_modules`, `CLAUDE.md`, `.mcp.json`, `.claude/skills` — plus a
hand-upgraded `uv 0.12.5`, a 1.4 GB `~/.cache/uv`, and a 166 MB `~/.npm`. Nothing
gitignored can come from a clone, so the working directory is on the snapshotted
filesystem, not a tmpfs. **The cached-install win is real**, which is what makes
`npm install` in the startup script near-free.

Caveat on what this proves: it demonstrates persistence across a restart of one
session's container. It does not by itself prove the snapshot taken for *new*
sessions in the environment contains the repo.

### Consequence for the design

Because the script is snapshotted once and shared across every repo that uses the
environment, a repo-specific clone cannot be relied on to be present when it runs.
So the work is split in two:

- `setup_env.sh` — the whole environment build. Pasted verbatim into the
  environment's setup script field, with only its `CONFIGURATION` block edited.
  Needs `BEST_EFFORT=true` there to satisfy constraint 2 above.
- `setup_startup.sh` — run by the agent at the start of a session. Verifies the
  hard dependencies the VM was supposed to provide, then tops up `uv sync` and
  `npm install` for the current branch. Warm, this measured **5.9 s**.
  *(Superseded — that figure was taken with a hot page cache. On a snapshot-started
  session the first run costs 22.9 s; see functional spec F9. This file is a dated
  record of what was measured at the time, so the number is left as written.)*

The `npm ci` / `npm install` split follows from the caching model: `npm ci` empties
`node_modules` before refilling it, so it belongs in the from-scratch build, while
the per-session top-up wants the incremental `npm install`. The `session-start-hook`
skill gives the same guidance: "prefer dependency install methods that take
advantage of [the cache] (i.e. prefer `npm install` over `npm ci`)."
