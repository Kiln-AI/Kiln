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
| `.config/utils/setup_env.sh` | `WARM_CACHE` / `--warm-cache`, the throwaway-clone warm-up, the provisioning marker | F9 |
| `.config/utils/setup_startup.sh` | New: per-session verify + dependency top-up | F8 |
| `.config/utils/setup_startup.sh` | Container gate, marker check, hardlink seed of `node_modules` | F8, F9 |
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

A clearly delimited block of five assignments at the very top of the file, above
everything else, holding the defaults for `HUMAN_MODE`, `UPGRADE_TOOLS`, `AGENT`,
`BEST_EFFORT` and `WARM_CACHE`. Flags override it.

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
--warm-cache       WARM_CACHE=true
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

### 1.3b Warming the machine, and the provisioning marker (F9)

Both live between §1.3 and the "needs a checkout" branch, so they run on the
no-checkout path that the cloud actually takes.

Paths, overridable so the behavior is testable without `/opt` or the network:

```bash
VM_SETUP_DIR="${KILN_VM_SETUP_DIR:-/opt/kiln-vm-setup}"
VM_SETUP_MARKER="$VM_SETUP_DIR/.setup_for_kiln_repo_v1"
WARM_NODE_MODULES="$VM_SETUP_DIR/node_modules"
KILN_REPO_URL="${KILN_REPO_URL:-https://github.com/Kiln-AI/Kiln.git}"
```

`warm_from_throwaway_clone` runs only when `WARM_CACHE=true` **and** `PROJECT_ROOT`
is empty. It clones into `$VM_SETUP_DIR` — not `/tmp` — so the `node_modules` move
at the end is a rename on one device rather than a 601 MB copy. It writes
`.python-version` into the clone *before* syncing, or uv caches wheels for the
wrong interpreter. Then the same parallel `uv sync` / `npm ci` pair as §1.4, an
`mv` of `app/web_ui/node_modules` to `$WARM_NODE_MODULES`, and `rm -rf` of the
clone.

Every failure in it is a **warning, not a `fail`**. The warm-up is an optimization;
routing it through `fail` would flip the closing line to "Resolve the errors above"
for a machine whose uv and Python are fine, and `setup_startup.sh` re-checks
per session everything that has to be true.

`write_vm_setup_marker` runs on **every** invocation, both paths, after the warm-up
so it can see whether a tree was made. Contents are for a human reading a broken
VM: `setup_version`, timestamp, uv version, Python pin, warm tree path,
`warm_node_modules_present`, `warm_node_modules_commit` and
`warm_node_modules_created_this_run`.

The first two of those describe **state**, not this run's history, and that
distinction is the point. A re-run without `--warm-cache` — which is exactly what
`AGENTS.md`'s repair command is — makes no tree while the existing one survives and
keeps being seeded from. Recording `created=false, commit=none` there would make
the marker lie about the provenance of the 601 MB every session inherits. So
`previous_marker_value` reads the prior marker and carries its commit forward
whenever the tree outlives the run that made it; `unknown` is reserved for a tree
with no marker to explain it.

If `$VM_SETUP_DIR` cannot be created — a local machine where `/opt` is not writable
— print one low-key note and continue. The marker only means something on a VM.

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

0. **Container gate**, after argument parsing and before root discovery. Nothing
   below this line should run on a development machine, so the check comes before
   the script even looks for a checkout.

   ```bash
   is_flag_set() {
     case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
       "" | false | f | 0 | no | n | off) return 1 ;;
       *) return 0 ;;
     esac
   }
   ```

   The falsy list is lowercased first and covers `false`, `f`, `0`, `no`, `n` and
   `off`: the documented rule is "non-empty and not falsy", and someone who sets
   `IS_CONTAINERIZED=no` and silently gets the opposite is the one failure of this
   gate that is impossible to notice.

   Applied to `CLAUDE_CODE_REMOTE` (Claude Code sets it to `true` in cloud sessions;
   confirmed live) and `IS_CONTAINERIZED` (manual escape hatch). Neither set: print
   the "not running in a VM/container" line plus what to do locally, and `exit 0`.
   Not `bad_environment` — this is a normal outcome, and a non-zero exit here would
   make every local invocation look like a broken machine.

0b. **Marker check**, right after root discovery and before the dependency gate,
   because a missing marker usually explains the failures that follow. Sets
   `VM_WAS_PROVISIONED=false` and prints a block naming the missing path and saying
   the VM setup script should have run. It does not exit: the only thing it forbids
   is step 3b's hardlink, since without the marker a tree at that path was not put
   there by this repo.

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

3b. **Seed `node_modules` by hardlink**, immediately before the sync, and only when
   all three hold: the checkout has no `node_modules`, `VM_WAS_PROVISIONED` is true,
   and `$WARM_NODE_MODULES` exists.

   All of it happens in a staging directory beside the target, and `node_modules`
   appears only as the final `mv -T` of a finished tree. Staging must be a sibling of
   the destination: staging inside `$VM_SETUP_DIR` would put the copy on the warm
   tree's filesystem and the `mv` would then copy 601 MB and drop every link it just
   made.

   Staging is gitignored and **per-PID**, and no run deletes or writes a staging path
   that is not its own. A shared name is measurably worse: racing two seed blocks on
   one name corrupted `node_modules` in **57 of 60** runs, each of them reporting a
   successful seed and exiting 0. Two shapes, both silent — one run's `rm -rf`
   unlinking entries out of the other's tree mid-`cp -al`, so the `mv -T` renames the
   survivors into place (1 to 3,225 entries against 12,402 expected); or that
   `rm -rf` failing against a directory still being created, after which the second
   `cp -al SRC DEST` copies *into* it and nests a whole tree (up to 24,805 entries).

   Concurrent runs in one checkout are not supported either way — they also collide
   on the `npm install` below, destructively and unconditionally — but a name that
   cannot collide costs nothing and keeps the damage in the one place already known
   to be broken.

   The cost of per-PID names is a leak: a killed run's staging keeps up to 601 MB
   under a name no later run will reuse. So the reclaim is an **age-based sweep** of
   `.node_modules.warm.*` older than an hour, which cannot be in flight since a seed
   takes about half a second. It runs unconditionally, outside the seed block, since
   that block is skipped as soon as `node_modules` exists — which is precisely the
   state a leaked directory would otherwise sit in forever. The seed itself clears
   only its own path, because a PID can be reused across a reboot.

   Order inside `seed_warm_node_modules`, which is load-bearing:

   1. `cp -al` the warm tree into staging.
   2. **Unshare the regular files at the root of staging**, `cp -p` + `mv -f` each.
      Hardlinks make an in-place write to the checkout a write to the pristine tree,
      and `npm install` does exactly that to `node_modules/.package-lock.json` —
      same inode, new mtime, measured, and reproduced in review. That file is npm's
      record of what is installed, so drift there is the one mutation that could
      make a later seeded session skip a missing package. Measured scope: after a
      seed, an `npm install` and a full `npm run build`, it was the only changed
      inode of 46,375; a review manifest of 52,031 entries across the full check
      suite found none.
   3. `mv -T` staging into place. `-T` does not make the rename always succeed — it
      makes a `node_modules` that appeared since the guard produce a failure rather
      than a staging directory silently nested inside it.

   Step 2 must precede step 3. If the tree were renamed first, there would be a
   window in which `node_modules` exists and is fully shared — and a run killed
   there leaves a checkout that the next run will *not* re-seed, since
   `node_modules` now exists, so its `npm install` writes straight through to the
   baseline. That is the exact corruption this step exists to prevent.

   The unshare list is collected with `mapfile` before the loop runs. Streaming
   `find` into it would have `find` reading the directory while `cp -p` and `mv -f`
   create and remove `X.unshared` names in it, and a transient entry in its readdir
   buffer would abort a seed that had nothing wrong with it.

   Every failure — including a failed unshare, which leaves the baseline exposed and
   so is not cosmetic — removes the staging directory and falls through to the sync
   populating `node_modules` from scratch. A cross-device image and a filesystem
   without hardlinks both land here. Diagnostics go to a temp file rather than a
   variable, and only the **first three lines plus a count** are printed: a
   cross-device warm tree fails once per file, measured at 46,436 lines and 15 MB,
   and this path's reader is usually an agent whose context that would bury. A
   *successful* seed prints the same capped summary when it had anything to say, so
   a warning is not swallowed by the happy path. The line count comes from
   `grep -c ''`, not `wc -l`: `wc` counts newlines, so a single unterminated error
   line would count as zero and print nothing — silence from the code written to
   break silence.

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
| Warm-up clone or its installs fail | warn to stderr, continue — an optimization, and the marker records that no tree was made |
| `$VM_SETUP_DIR` not writable | one note, continue — the marker only matters on a snapshotted VM |
| Not containerized (`setup_startup.sh`) | print one line, exit 0 — a normal outcome |
| Marker missing (`setup_startup.sh`) | prominent warning, skip the hardlink, continue |
| `cp -al` of the warm tree fails | note with the `cp` error, continue — `npm install` fills `node_modules` instead |

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

For F9, with `KILN_VM_SETUP_DIR` and `KILN_REPO_URL` standing in for `/opt` and the
network so each case is executed rather than reasoned about:

6. `setup_startup.sh` with neither container variable set, and with each of `false`,
   `0` and empty: one line, exit 0, checkout untouched. With `IS_CONTAINERIZED=true`
   alone: full run.
7. Marker absent with a warm tree present: warning, no hardlink, exit 0. Marker
   present with no warm tree: no warning, no seed. `node_modules` already present:
   no seed.
8. Marker and warm tree present with no `node_modules`: seeded, and `stat` shows the
   **same inode** on both sides, with `du` of the two trees together showing one
   copy's worth of blocks.
9. Warm tree on another filesystem (`/dev/shm`): `cp -al` reports the cross-device
   error, the note is printed, no staging directory is left, `npm install` runs.
10. In-place-write probe: a full-tree inode/size/mtime manifest of the warm tree
    before and after a seed plus `npm install` plus `npm run build`.
11. `setup_env.sh --warm-cache` with no checkout: clone, sync, warm tree kept,
    clone deleted, marker records the commit. With a checkout: no clone, marker
    records `warm_node_modules_created_this_run=false`.

For the `conftest.py` change specifically:

- Full suite must report **6369 passed, 10020 skipped, 0 errors** — the same
  counts as before the change. A drop in either number means tests stopped
  running, which is the dangerous failure mode here.
- A single small test file (`libs/core/kiln_ai/utils/test_config.py`) runs in
  ~1 s, down from ~7 s.
- `uv run ./checks.sh --agent-mode` exits 0.
