---
status: complete
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
| `CONTRIBUTING.md` | Point its setup section at the script, the uv floor, and `.python-version` | F7 |
| `.config/wt/README.md` | Point its setup line at `--human`, now that the workspace offer is behind that flag | F1 |
| `.agents/mcp.json` | Add the `hooks-mcp>=0.2.5` floor | "Dependency on upstream" |

No changes to `checks.sh`, the `Makefile`, `.config/hooks_mcp.yaml`, the schema
scripts, `.agents/skills/*`, or any `app/`/`libs/` source. Their plain `uv run`
calls become correct once uv ≥ 0.10 is enforced — 0.07 s, no lockfile churn.

## 1. `.config/utils/setup_env.sh`

Structure, in order. `set -uo pipefail` at the top — deliberately **not** `set -e`,
because `--best-effort` has to control the exit code, which means failures are
recorded explicitly rather than aborting the shell.

`pipefail` is not POSIX, so a runner that ignores the shebang and starts the file
with `sh` would die on that line — before `--best-effort` could suppress the exit
code, which as a cloud setup script means the session never starts. The file
therefore re-execs itself under bash when `BASH_VERSION` is unset.

### 1.0 The `CONFIGURATION` block

A clearly delimited block of four assignments at the very top of the file, above
everything else, holding the defaults for `HUMAN_MODE`, `UPGRADE_TOOLS`, `AGENT`
and `BEST_EFFORT`. Flags override it.

This block is the file's contract with the cloud environment: the whole script is
pasted into the environment dialog and only this block is edited. Keep it a
contiguous run of plain assignments with a comment naming the cloud values, so
editing it in a web form is unambiguous.

The block is the only thing a human edits, but that is a statement about the
editing workflow, not a claim that the rest of the file is location-independent by
default. It is not, unless the script discovers its project root at runtime — see
§1.0b, which is what makes the "edit only this block" promise true.

### 1.0b Project root discovery

The script must not derive `PROJECT_ROOT` from `${BASH_SOURCE[0]}`. Pasted into a
cloud setup field the file does not live in `<repo>/.config/utils/`, so that
derivation points two directories above wherever the platform stashed the script —
never the checkout. Fed on stdin, `BASH_SOURCE` is unset entirely, and under
`set -u` the command substitution dies while the parent continues with
`PROJECT_ROOT=/`; running as root, the `.python-version` write then lands at
`/.python-version`.

So: discover, then validate. A candidate is a Kiln root when it has both
`pyproject.toml` and `libs/core/kiln_ai/`. Candidates, in order:

1. `../..` from `${BASH_SOURCE[0]:-$0}` — the checkout the file lives in, when it
   is running from one.
2. `git rev-parse --show-toplevel` — the checkout we are standing in.
3. Walking up from `$PWD`.

If none validates, `PROJECT_ROOT` is empty and **that is not an error**. A cloud
setup script runs once per environment, is snapshotted, and is shared across every
repo using it (research §12), so no checkout is the normal case there. The script
does the environment-level work it can — the uv gate and `uv python install 3.13`,
both worth baking into a snapshot — then prints one notice naming what it skipped
and exits through `finish`. It must not emit a series of `error:` lines for
something that is not a failure.

`setup_startup.sh` (§1B) is what then guarantees a correct per-session state in
the checkout, and the notice points at it.

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
exits 0.

Every path that reaches the *work* goes through `finish`. There are exactly three
direct exits, all of them before any work starts and none of them reachable from a
correct invocation:

| Where | Exit | Why not `finish` |
|---|---|---|
| Unknown flag, bad `--agent` | 2 | F1 makes the code unconditional, and `--best-effort` may not be parsed yet |
| `--help` | 0 | Nothing ran |
| Bash guard, `$0` unreadable | 1 | The shell cannot run the script at all; `fail`/`finish` are not defined yet |

So the `--best-effort` guarantee is "no failure during setup produces a non-zero
exit", not "this script can never exit non-zero". A malformed invocation or a shell
that cannot run bash still can, which is correct: both are configuration errors a
human must see, and the cloud environment's own invocation is fixed and reviewable.

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

Check that uv exists *before* any of this. Every branch below runs uv, so none of
them can help when it is absent — warning that `uv (not installed)` is "older than
0.10.0" and then offering an upgrade command that cannot run is confusing rather
than useful. Missing uv is its own `fail` + `finish`.

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
- After upgrading, run `hash -r` and re-read `uv --version`. Bash has already
  hashed the old `uv` from the version check, and the new binary usually lands at
  a different path (`~/.local/bin/uv`), so without this the rest of the run keeps
  calling the uv that was just replaced. If the re-read is still below `UV_MIN`
  the new binary is shadowed on `PATH`; that is a `fail`, not a success.

### 1.3 Python 3.13

```bash
uv python install 3.13          # not repo-specific: always run
# ... then, only with a checkout:
echo "3.13" > "$PROJECT_ROOT/.python-version"
```

`uv python install` is idempotent and costs ~2.2 s on a cold cache. It runs even
when no checkout was found, since a pre-installed interpreter is exactly what is
worth capturing in an environment snapshot.

`.python-version` is what makes the pin survive `.venv` deletion, because uv
consults it on every later sync. It is also written by `setup_startup.sh` (§1B),
which is what establishes the pin in a fresh sandbox where this script ran against
no checkout at all.

### 1.4 Parallel dependency install

```bash
uv sync --frozen --all-packages & py_pid=$!
( cd "$PROJECT_ROOT/app/web_ui" && npm ci --no-fund --no-audit ) & npm_pid=$!

py_status=0;  wait "$py_pid"  || py_status=$?
npm_status=0; wait "$npm_pid" || npm_status=$?
```

Both are waited on before evaluating either, so one failing does not leave the
other orphaned, and both failures are reported rather than only the first. If
either is non-zero, print which failed and exit 1.

`wait` needs `|| status=$?` under `set -e`. Interleaved output from the two jobs
is acceptable; do not add log-capture machinery for it.

`--no-fund --no-audit` on both npm calls: the funding block and the audit's
vulnerability tally read like failures to anyone scanning a cloud setup log, and
neither affects what gets installed.

### 1.5 Agent configuration

For `all` run both; for `claude`/`cursor` run that one; for `none` skip. Each is
guarded by a file-existence check — warn and continue if a script is missing, do
not fail the run. A script that exists but fails is a `fail`, not a warning.

The path must be absolute, off `$PROJECT_ROOT`. A relative `.agents/$1/setup.sh`
would depend on the working directory, which is exactly the bug class §1.0b exists
to remove.

```bash
run_agent_setup() {  # $1 = claude|cursor
  local script=".agents/$1/setup.sh"
  if [ -f "$PROJECT_ROOT/$script" ]; then
    bash "$PROJECT_ROOT/$script" || fail "$script failed"
  else
    echo "warning: $script not found, skipping" >&2
  fi
}
```

This step is reachable only with a checkout (§1.0b). In the cloud that usually
means it does not run here at all, which is why §1B repeats it.

### 1.6 `--human` extras

The existing worktrunk/zellij block, moved behind `if [ "$human_mode" = true ]`.
It keeps its current `read -rp` prompt; that is the one place interactivity is
correct. Nothing else in the script may block on input except the uv prompt in
§1.2, which is bounded by its 10 s timeout.

The block cannot move over verbatim: it was written under `set -e`, where the
first failing `brew install` aborted the script. There is no `set -e` now, so each
install needs `|| fail ...` or it will report success after failing. Same for the
worktrunk config symlink, and the closing "Workspaces ready!" line, which must not
print when something failed.

## 1B. `.config/utils/setup_startup.sh`

New file. Same bash re-exec guard and `set -uo pipefail` as §1, and the same
`is_kiln_root` / `find_kiln_root` discovery as §1.0b — the `${BASH_SOURCE[0]}`
derivation is the identical bug here, and worse: `cd ""` succeeds as a no-op, so a
body fed on stdin silently yields `PROJECT_ROOT=$PWD/../..` and the script writes
and syncs two directories above the working directory. The one difference from §1
is what a miss means: this script has nothing useful to do without a checkout, so
no root is fatal, not a skip.

Order is load-bearing:

1. **Hard dependency gate.** `uv` on `PATH`; `uv --version` non-empty and ≥
   `UV_MIN` using the same `sort -V` comparison as §1.2; `npm` on `PATH`. Any
   failure calls `bad_environment` and exits 1.

   This must run **before** the sync. A too-old uv is what rewrites `uv.lock`, so
   a check placed after the sync would fire only once the damage was done.

   The comparison is duplicated from §1.2 rather than shared, because §1.2's file
   is pasted whole into a web form and cannot source anything. Both copies carry a
   comment saying to keep them in sync. This copy needs the empty-version guard
   too: without it an empty `uv --version` reads as `uv  is older than 0.10.0`.

2. **Agent configuration**, the same work as §1.5, unconditional but not identical. This is the step
   that makes F5 reachable at all in a sandbox: §1.0b means `setup_env.sh` usually
   has no checkout to write into, so without this, `CLAUDE.md`, `.claude/skills/`
   and `.mcp.json` never exist in a session.

   It goes here, ahead of the pin and the sync, because it is offline and
   sub-second and it is what makes the repo's instructions readable — it must not
   be gated behind work that can fail. A per-agent script that is missing is
   skipped silently; one that fails prints its captured output as a warning and
   does not stop the run, since a stale `CLAUDE.md` still beats aborting.

   Both differences from §1.5 are deliberate and worth a comment in the code, since
   they otherwise read as drift. §1.5 warns about a missing script because `--agent`
   named it explicitly and its absence is a surprise; here there is no selector and
   the script runs every session, so silence is right. §1.5 treats a failure as a
   `fail` because it is building an environment; here it is a warning, because
   aborting a startup check over agent config would cost more than it saves.

3. **Pin the Python version.** Write `PYTHON_PIN` to `.python-version` when it is
   missing, malformed, or below `PYTHON_MIN_MINOR`, *before* the sync.

   This is what gives F3 a path in a fresh sandbox. `setup_env.sh` is snapshotted
   and shared across repos, so in the cloud it may never have run against this
   checkout — and without the pin, the sync below builds `.venv` on the system
   Python, whose build has no `tkinter`. Checking afterwards would only produce a
   `bad_environment` round trip through a human. uv reads the file on every sync,
   so writing it here is enough; the condition keeps the script a no-op on the warm
   path.

   Compare against the floor, not for equality. `PYTHON_MIN_MINOR` is a minimum, so
   a contributor deliberately pinned to a *newer* 3.x must not have it reset — and
   silently reset every run, since the next sync would then rebuild their venv.

   Compare major and minor only, ignoring any patch component. `3.13.1` is the form
   pyenv writes, and `AGENTS.md` tells pyenv users this file is shared with their
   shims, so a comparison that drops the patch and then fails to match would clobber
   precisely the pins most likely to be deliberate.

4. **Sync**, both in parallel, same `wait`-both pattern as §1.4:
   `uv sync --frozen --all-packages` and `npm install --no-fund --no-audit`.
   `npm install`, not `npm ci` — see F4.

   `npm install` can rewrite the tracked `package-lock.json`, which nothing else in
   either script does. Hash the file with `cksum` before and after and warn, naming
   it and the revert command, when it changed. Not a failure — the change may be
   what the branch intended — but it must not be silent, since every other step is
   careful not to touch a tracked file.

5. **Post-sync verification**, via a single `uv run --frozen python -c` that prints
   the major version, minor version, and whether `tkinter` resolves. Placed after
   the sync because both facts are properties of `.venv`. A `tkinter` check uses
   `importlib.util.find_spec` rather than a real import, so it does not need a
   display. Capture the probe's stderr and print it on failure — "could not run
   Python from .venv" alone gives the reader nothing to act on.

   Parse defensively: read the *last* line of the probe output and require the two
   version fields to be digits. Anything uv prints on stdout would otherwise reach
   an arithmetic test, which emits a raw bash `integer expression expected` and then
   falls through to the misleading "no tkinter" verdict.

`bad_environment` is the single failure path for "this VM is wrong", so the shape
of the message is written once and every check gets the same framing, naming both
the local and sandbox cases.

It takes the repair line as an argument rather than hardcoding one. Of its nine
reasons, five are fixed by `setup_env.sh --upgrade-tools` — an unreadable uv
version, a too-old uv, and the three `.venv` verdicts — but a single global repair
line would be wrong for the other four. `setup_env.sh` never installs npm and needs
a working uv in order to upgrade uv, so those two point at the upstream installers;
a failed `.python-version` write points at the checkout's permissions; and "no Kiln
checkout found" points at changing directory.

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
def _litellm_per_test_setup() -> None:
    # Importing litellm costs ~4s. Most test modules never touch it, so only do
    # litellm-specific setup once something has imported it. The name says what it
    # does now: it is no longer only an httpx-client clear, and it has no teardown.
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

### Log-path verification — confirmed, with a recorded ordering dependency

`setup_litellm_logging` now resolves its log path lazily during a test, while the
autouse `use_temp_settings_dir` fixture has `Config.settings_path` patched. The
concern was that the log could follow the patched path into `tmp_path`.

Verified by running a test module that imports `litellm` and inspecting the
`ModelCalls` logger's handler: `baseFilename` is `~/.kiln_ai/logs/test_model_calls.log`,
unchanged from before. `get_log_file_path` reads `Config.settings_dir()`
(`config.py:288`), which builds its path from `Path.home()` and is not the method
`use_temp_settings_dir` patches. No session-scoped fallback fixture is needed.

That probe covers `settings_path`, but it is not the whole story, and the rest
belongs on the record rather than in a "confirmed" one-liner. Moving path
resolution from a session-scoped fixture into a function-scoped one makes it
**order-dependent**: two modules —
`libs/core/kiln_ai/adapters/vector_store/test_lancedb_adapter.py:47` and
`test_vector_store_registry.py:16` — do patch `Config.settings_dir` itself to
`tmp_path`, through their own autouse fixtures. If one of those ran first, its
`tmp_path` would be baked into the rotating file handler and, because
`setup_litellm_logging` is idempotent, stay there for the rest of the worker.

This is correct today because pytest instantiates autouse fixtures from the root
conftest before module-level ones, so the real path always wins the race. That is
a documented pytest property rather than an accident, but it is load-bearing and
now unobvious, so it is called out in a comment on the fixture. Anyone changing
fixture scopes here should re-check it.

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
