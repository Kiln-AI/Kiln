---
status: draft
---

# Architecture: Cloud Sandbox Developer Experience

Small project — no component designs. Every change is listed here with enough
detail that no design decisions remain for the implementer.

## Change inventory

| File | Change | Feature |
|---|---|---|
| `.config/utils/setup_env.sh` | Rewrite: config block, flags, uv check, py3.13, parallel installs, agent config | F1–F5 |
| `.config/utils/setup_startup.sh` | New: per-session verify + dependency top-up | F8 |
| `pyproject.toml` | Add `required-version = ">=0.10"` to `[tool.uv]` | F2 |
| `.gitignore` | Add `.python-version` | F3 |
| `conftest.py` | Defer the `litellm` import | F6 |
| `AGENTS.md` | Add an environment-setup section | F7 |

No changes to `checks.sh`, the `Makefile`, `.config/hooks_mcp.yaml`, the schema
scripts, `.agents/skills/*`, or any `app/`/`libs/` source. Their plain `uv run`
calls become correct once uv ≥ 0.10 is enforced — 0.07 s, no lockfile churn.

## 1. `.config/utils/setup_env.sh`

Structure, in order. `set -uo pipefail` at the top — deliberately **not** `set -e`,
because `--best-effort` has to control the exit code, which means failures are
recorded explicitly rather than aborting the shell.

### 1.0 The `CONFIGURATION` block

A clearly delimited block of four assignments at the very top of the file, above
everything else, holding the defaults for `HUMAN_MODE`, `UPGRADE_TOOLS`, `AGENT`
and `BEST_EFFORT`. Flags override it.

This block is the file's contract with the cloud environment: the whole script is
pasted into the environment dialog and only this block is edited. Keep it a
contiguous run of plain assignments with a comment naming the cloud values, so
editing it in a web form is unambiguous. Nothing below it may need changing to
make the script correct in the cloud.

### 1.1 Argument parsing

```
--human            HUMAN_MODE=true
--upgrade-tools    UPGRADE_TOOLS=true
--best-effort      BEST_EFFORT=true
--agent VALUE      AGENT=VALUE   (all|claude|cursor|none, default all)
--help             usage; exit 0
*                  usage to stderr; exit 2
```

Validate `--agent` against the four allowed values; anything else is exit 2.
`--agent` also accepts `--agent=VALUE`.

### 1.1b Failure accounting

`fail <message>` prints to stderr and sets `FAILED=1`. `finish` exits 1 when
`FAILED` is set, unless `BEST_EFFORT=true`, in which case it says so on stderr and
exits 0. Every exit path goes through `finish`.

### 1.2 uv version gate

```bash
UV_MIN=0.10.0
uv_version=$(uv --version 2>/dev/null | awk '{print $2}')
uv_too_old() {
  [ -z "$uv_version" ] && return 0
  [ "$(printf '%s\n%s\n' "$UV_MIN" "$uv_version" | sort -V | head -1)" != "$UV_MIN" ]
}
```

`sort -V` semantics: the comparison asks whether `UV_MIN` sorts first. Equal
versions sort to `UV_MIN`, so `uv_too_old` is false — correct. Verified against
0.8.17 (too old), 0.10.0 (ok), 0.12.5 (ok).

Then branch exactly as F2 specifies:

```bash
if uv_too_old; then
  if [ "$upgrade_tools" = true ]; then
    uv tool install --force uv
  elif [ -t 0 ]; then
    ans=""
    read -t 10 -rp "uv ${uv_version:-<none>} is too old (need >= $UV_MIN). Upgrade? [Y/n] " ans || true
    case "$ans" in
      [Nn]*) echo "Skipped. Expect uv.lock churn and broken imports." ;;
      *)     uv tool install --force uv ;;
    esac
  else
    echo "WARNING: uv ${uv_version:-<none>} is too old (need >= $UV_MIN)." >&2
    echo "         Re-run with --upgrade-tools, or: uv tool install --force uv" >&2
  fi
fi
```

Notes for the implementer:

- `read -t` returns non-zero on timeout, so it needs `|| true` under `set -e`.
  On timeout `ans` stays empty and falls into the `*)` branch — upgrade. This is
  the intended default.
- `--force` is mandatory. Without it uv downloads and then aborts with
  `error: Executables already exist: uv, uvx`.
- Do **not** use `uv self update` — it resolves releases through the GitHub API,
  which is rate-limited per egress IP and fails on shared sandbox IPs. Verified
  twice.
- Do **not** use pip.
- No version pin — always latest.
- After upgrading, re-read `uv --version` if any later logic depends on it.

### 1.3 Python 3.13

```bash
uv python install 3.13
echo "3.13" > "$PROJECT_ROOT/.python-version"
```

`uv python install` is idempotent and costs ~2.2 s on a cold cache.
`.python-version` is what makes the pin survive `.venv` deletion.

### 1.4 Parallel dependency install

```bash
uv sync --frozen --all-packages & py_pid=$!
( cd "$PROJECT_ROOT/app/web_ui" && npm ci ) & npm_pid=$!

py_status=0;  wait "$py_pid"  || py_status=$?
npm_status=0; wait "$npm_pid" || npm_status=$?
```

Both are waited on before evaluating either, so one failing does not leave the
other orphaned, and both failures are reported rather than only the first. If
either is non-zero, print which failed and exit 1.

`wait` needs `|| status=$?` under `set -e`. Interleaved output from the two jobs
is acceptable; do not add log-capture machinery for it.

### 1.5 Agent configuration

For `all` run both; for `claude`/`cursor` run that one; for `none` skip. Each is
guarded by a file-existence check — warn and continue if a script is missing, do
not fail the run.

```bash
run_agent_setup() {  # $1 = claude|cursor
  local s=".agents/$1/setup.sh"
  if [ -f "$s" ]; then bash "$s"; else echo "warning: $s not found, skipping" >&2; fi
}
```

### 1.6 `--human` extras

The existing worktrunk/zellij block, moved behind `if [ "$human_mode" = true ]`.
It keeps its current `read -rp` prompt; that is the one place interactivity is
correct. Nothing else in the script may block on input except the uv prompt in
§1.2, which is bounded by its 10 s timeout.

## 1B. `.config/utils/setup_startup.sh`

New file. `set -uo pipefail`. Order is load-bearing:

1. **Hard dependency gate.** `uv` on `PATH`; `uv --version` ≥ `UV_MIN` using the
   same `sort -V` comparison as §1.2; `npm` on `PATH`. Any failure calls
   `bad_environment`, which prints the repair command and exits 1.

   This must run **before** the sync. A too-old uv is what rewrites `uv.lock`, so
   a check placed after the sync would fire only once the damage was done.

2. **Sync**, both in parallel, same `wait`-both pattern as §1.4:
   `uv sync --frozen --all-packages` and `npm install --no-fund --no-audit`.
   `npm install`, not `npm ci` — see F4.

3. **Post-sync verification**, via a single `uv run --frozen python -c` that prints
   the major version, minor version, and whether `tkinter` resolves. Placed after
   the sync because both facts are properties of `.venv`. A `tkinter` check uses
   `importlib.util.find_spec` rather than a real import, so it does not need a
   display.

`bad_environment` is the single failure path for "this VM is wrong", so the repair
instructions are written once and every check gets the same message. It names both
the local and sandbox cases, since the same script serves both.

## 2. `pyproject.toml`

```toml
[tool.uv]
required-version = ">=0.10"
exclude-newer = "7 days"
```

`exclude-newer` is unchanged. This makes a too-old uv fail loudly at the point of
use instead of silently re-resolving.

## 3. `.gitignore`

Add `.python-version`. It sits near the existing `CLAUDE.md` / `.claude/` /
`.mcp.json` entries, which are generated files in the same spirit.

## 4. `conftest.py`

Current top-of-file has `import litellm` at module scope and
`from kiln_ai.datamodel.basemodel import KilnAttachmentModel`. Both go.

```python
import sys
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from kiln_ai.datamodel.basemodel import KilnAttachmentModel


@pytest.fixture(autouse=True)
def _clear_httpx_clients() -> None:
    # Importing litellm costs ~4s. Most test modules never touch it, so only do
    # litellm-specific setup and teardown once something has imported it.
    litellm = sys.modules.get("litellm")
    if litellm is None:
        return

    from kiln_ai.utils.logging import setup_litellm_logging

    setup_litellm_logging("test_model_calls.log")
    litellm.in_memory_llm_clients_cache.flush_cache()
```

The session-scoped `setup_test_logging` fixture is **deleted**; its body is folded
into the guarded path above. The attachment factory takes a local import and a
quoted return annotation:

```python
    def create_attachment(
        mime_type: MockFileFactoryMimeType,
        text: str | None = None,
    ) -> "KilnAttachmentModel":
        from kiln_ai.datamodel.basemodel import KilnAttachmentModel
        ...
```

### Why this is correct

- **The cache flush is never wrongly skipped.** It is skipped only when `litellm`
  is absent from `sys.modules`, i.e. nothing has imported it, so there are no
  cached HTTP clients to flush. No cross-test state can leak.
- **Logging is still configured once.** `setup_litellm_logging` early-returns if a
  `CustomLiteLLMLogger` is already in `litellm.callbacks`
  (`libs/core/kiln_ai/utils/logging.py:137-140`), so calling it per-test is
  idempotent — every call after the first is a short list scan.
- **Import ordering holds.** pytest imports the root conftest before collecting
  test modules, and any module that uses litellm imports it at its own module
  scope, so by the time that module's tests run, `sys.modules` has it.

### Open verification item

`setup_litellm_logging` now resolves its log path lazily during a test, while the
autouse `use_temp_settings_dir` fixture has `Config.settings_path` patched. The
function reads `Config.settings_dir()` — a different method — so it is expected to
be unaffected, but the implementer must **confirm** the model-calls log still
lands where it did before, rather than assume. If it does move, keep a
session-scoped fixture that only does the logging setup, still guarded on
`sys.modules`.

## 5. `AGENTS.md`

A short section covering: `setup_env.sh` as the way to set up an environment, the
flag table, the `--frozen` consequence (run `uv lock` first if you changed
dependencies), and that `CLAUDE.md` is generated from `AGENTS.md` and overwritten
on every run — so personal notes belong in `~/.claude/CLAUDE.md`.

Keep it brief. Do not paste the research numbers in; link the spec folder.

## Error handling strategy

| Condition | Behavior |
|---|---|
| Unknown flag / bad `--agent` | usage to stderr, exit 2 |
| uv too old, `--upgrade-tools` | upgrade; if the upgrade fails, exit non-zero |
| uv too old, TTY, declined | warn, continue (user's call) |
| uv too old, no TTY | warn to stderr, continue — `required-version` catches it later |
| `uv sync` or `npm ci` fails | name which one, exit 1 |
| Agent setup script missing | warn, continue |
| `uv python install 3.13` fails | exit non-zero — everything downstream depends on it |

The script is not idempotency-sensitive: every step is safe to re-run.

## Testing strategy

This is shell and config, so there are no unit tests to add. Validation is
behavioral, run in a **fresh** cloud sandbox — a re-run in an already-fixed
session proves nothing:

1. The nine success criteria in the functional spec, in order.
2. `setup_env.sh --help`, an unknown flag, and `--agent bogus` all exit 2 with
   usage.
3. `--agent none` writes no `CLAUDE.md`, `.claude/`, or `.cursor/`.
4. With a deliberately downgraded uv and no TTY, the script warns and continues;
   with `--upgrade-tools`, it upgrades.
5. `git status --porcelain` empty after every variation.

For the `conftest.py` change specifically:

- Full suite must report **6369 passed, 10020 skipped, 0 errors** — the same
  counts as before the change. A drop in either number means tests stopped
  running, which is the dangerous failure mode here.
- A single small test file (`libs/core/kiln_ai/utils/test_config.py`) runs in
  ~1 s, down from ~7 s.
- `uv run ./checks.sh --agent-mode` exits 0.
