---
status: complete
---

# Phase 6: Close the Circular Bootstrap with a User-Level `SessionStart` Hook

## Overview

The project's one remaining known limitation (F5) is that nothing tells an
unattended cloud agent to run `setup_startup.sh`. The instruction lives in
`AGENTS.md` → `CLAUDE.md`, and `CLAUDE.md` is written *by* that script, so in a
fresh sandbox the agent has never been told the script exists. The plan carried
this as an operator-side prompt a human must write, plus a deferred decision about
a tracked `.claude/settings.json`.

Both are now obsolete. Claude Code loads a **user-level** `~/.claude/settings.json`
in cloud sessions, `~/.claude/` is on the snapshotted filesystem, and hooks
registered there fire. So the VM setup script can install the hook itself: no repo
file, no tracked `.claude/`, no human instruction, and the loop closes before the
agent's first turn.

`setup_env.sh` gains `--create-startup-script` / `CREATE_STARTUP_SCRIPT` (default
**false**, so a local run never touches a contributor's Claude Code settings). It
writes a shim into `$VM_SETUP_DIR` and merges a `SessionStart` entry pointing at it
into the user's `settings.json`.

### The risk that had to be settled first: does this displace the launcher's hook?

Claude Code cloud sessions already run a `SessionStart` hook from
`~/.claude/launcher-settings.json` — `session-start-git-identity.sh`, which pins
`user.email` to `noreply@anthropic.com` and installs the `commit-msg` trailer hooks
that make commits verify on GitHub. If adding `hooks.SessionStart` to
`settings.json` *replaced* that, this phase would silently break commit signing in
every later session: a far worse outcome than the problem being solved.

It does not. Two independent confirmations:

1. **Empirical, on this machine.** A real `claude -p` run with an isolated
   `HOME`/`CLAUDE_CONFIG_DIR`, a user `settings.json` carrying one `SessionStart`
   hook and a `--settings` file carrying another (the exact arrangement CCR uses —
   `ps` shows the live session was spawned with
   `--settings /root/.claude/launcher-settings.json`), fired **both** hooks: both
   marker files were written, and the `--settings` file's `Stop` hook fired too.

2. **In the implementation.** Settings sources are merged in order
   `userSettings, projectSettings, localSettings, flagSettings, policySettings`
   with a lodash `mergeWith` customizer whose array rule is
   `if (Array.isArray(a) && Array.isArray(b)) return uniq([...a, ...b])`. Hook
   arrays therefore **concatenate** across sources rather than override. (The one
   documented way to lose the launcher's hooks is `disableAllHooks: true` in repo
   settings, which the runner explicitly warns about — this phase does not set it.)

So the launcher hook and the Kiln hook both run, and the ordering (user settings
first) does not matter: neither depends on the other.

### The costs, stated plainly

- **Session start gets slower, synchronously.** Measured on snapshot-started
  sessions, the first `setup_startup.sh` of a session costs **22.9 s** with the
  warm `node_modules` tree present. That is now paid before the agent's first turn,
  every session. It is not new work — it is work that had to happen anyway,
  moved to where it cannot be skipped — but the user feels it as latency at the
  prompt rather than as a tool call.
- **Async mode is available and is deliberately not used.** A hook can return
  `{"async": true}` and finish in the background. That would hide the latency and
  break the point: `CLAUDE.md`, `.claude/skills/` and `.mcp.json` are read when the
  session's context is assembled, so a background write of them can lose the race
  it exists to win, non-deterministically. Correctness over latency.
- **It runs in sessions nobody asked for it in.** Every session on the VM, for
  every repo sharing the environment. That is why the shim exits 0 immediately when
  the session's directory is not a Kiln checkout, and why `setup_startup.sh`'s own
  container gate is a second line of defence.

## Steps

1. **`.config/utils/setup_env.sh` — `CREATE_STARTUP_SCRIPT` in the `CONFIGURATION`
   block**, default `false`, and named in the "for a Claude Code cloud setup script
   use" comment alongside the other three.

2. **`setup_env.sh` — `--create-startup-script` flag** in the parser and in
   `usage`.

3. **`setup_env.sh` — paths**, beside the existing `VM_SETUP_DIR` constants:

   ```bash
   STARTUP_HOOK_SHIM="$VM_SETUP_DIR/kiln_session_start_hook.sh"
   CLAUDE_USER_SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
   ```

   `CLAUDE_CONFIG_DIR` is what Claude Code itself honors for the user settings
   location, so respecting it is both correct and what makes the whole thing
   testable against a temp directory. The shim's basename is repo-specific on
   purpose: it is the idempotency key in step 5.

4. **`setup_env.sh` — write the shim.** The hook fires for *every* repo in a shared
   environment, so the shim must find a Kiln checkout or do nothing:

   ```bash
   dir="${CLAUDE_PROJECT_DIR:-$PWD}"
   dir="$(cd "$dir" 2>/dev/null && pwd)" || dir="$PWD"
   while [ ! -f "$dir/.config/utils/setup_startup.sh" ]; do
     parent="$(dirname "$dir")"
     [ "$parent" = "$dir" ] && exit 0   # "/" and "." are their own parents
     dir="$parent"
   done
   ```

   `CLAUDE_PROJECT_DIR` is set for `SessionStart` hooks — verified by running a
   probe hook, which also showed it is the session's working directory, *not* the
   git root. In a cloud session those are the same thing, but the walk upward costs
   nothing and covers a session started in a subdirectory. `setup_startup.sh` does
   its own root discovery, so an odd cwd is survivable either way.

   The original sketch's `bash "$s" || true` grew two things while being built, both
   of which rule out the `exec` it also sketched:

   - **Both streams are captured and re-emitted on stdout**, because only stdout
     becomes session context, while every failure message in `setup_startup.sh`
     goes to stderr. `exec` would hand the agent a silent failure.
   - **The captured text is capped** at ~4 KB, keeping the head and the tail, with
     a `[...trimmed...]` line between. The normal run is ~15 lines, but this text is
     spent from the context window rather than scrolled past, and a failing `uv`
     resolution or `npm install` is unbounded. The tail matters most — that is
     where the reason is — so a plain `head` would have been the wrong cap.

   `</dev/null` because the hook's stdin is the event JSON and nothing below should
   read it. The shim exits 0 unconditionally, appending one line naming the exit
   status when the script failed.

5. **`setup_env.sh` — merge the hook entry into `settings.json` with `python3`.**
   Merging is mandatory: that file already carries `enableAllProjectMcpServers:
   true` and clobbering it would silently disable the project's MCP servers. The
   embedded script:

   - Missing or empty file → start from `{}`. Non-existent parent directory →
     create it.
   - Invalid JSON, or a top-level value that is not an object, or `hooks` /
     `hooks.SessionStart` of the wrong type → **refuse and leave the file exactly as
     it is**, with a message naming the file. Repairing someone's malformed settings
     is not this script's business, and truncating them is worse than not
     installing.
   - Idempotency: drop any existing `SessionStart` command containing the shim's
     repo-specific basename (which also self-heals a `KILN_VM_SETUP_DIR` that
     moved), then append one entry. Groups left empty by that filter are removed;
     groups holding anything else keep it. Every unrelated `SessionStart` entry
     survives untouched.
   - Entry shape: a group with `"matcher": "startup|resume|fork"` holding
     `{"type": "command", "command": "<shim>", "timeout": 600, "statusMessage":
     "Preparing the Kiln checkout"}`. The matcher is a regex over the event's
     `source`, whose values are `startup, resume, clear, compact, fork` (read out of
     the CLI's own schema). `clear` and `compact` are excluded deliberately: the
     re-run would be a cheap no-op, but it would re-inject the hook's output into
     the context window, and a long session compacts repeatedly. `timeout` is in
     seconds and generous on purpose — a VM whose warm tree is missing pays ~32 s,
     and a branch that really changed dependencies pays more.
   - Write to a temp file in the same directory and `os.replace` over the target,
     preserving the existing file's mode, so a failed write cannot truncate live
     settings. `ensure_ascii=False`, or the dump would rewrite non-ASCII characters
     in someone else's unrelated setting as escapes — semantically equal, but this
     function's whole contract is that it touches nothing but its own entry. Report
     whether anything changed.

   Failures are warnings, not `fail`s, for the same reason as the warm cache: this
   is a convenience layer, and a VM whose uv and Python are fine should not close
   with "Resolve the errors above". Also skip with one line when `python3` is
   absent.

6. **`setup_env.sh` — call it** just before `write_vm_setup_marker`, so the marker
   can record the outcome, and well before the "everything below needs a checkout"
   exit — the cloud environment-build case has no checkout and is exactly the case
   this exists for.

   The marker gains one field, `session_start_hook`, keyed off a
   `STARTUP_HOOK_INSTALLED` flag that only a successful *registration* sets. The
   shim file existing is not the same fact: it is written before the merge, and the
   merge refuses to touch a malformed `settings.json`, so a field keyed off the file
   would report a working hook on a VM that has none — and send whoever is reading
   the marker away from the one failure it exists to record. Three values:
   the path when this run installed it, `registration_failed` when this run tried
   and could not, and otherwise the previous marker's answer carried forward (the
   same rule the warm tree's commit follows), defaulting to `none`.

   The `_v1` contract version does not move: `setup_startup.sh` only tests that the
   marker exists, and a VM without the hook is not a VM that is set up wrong.

7. **`AGENTS.md`** gains the flag in its `setup_env.sh` table and a note on what the
   hook is, where it is installed, and that it merges rather than replaces. (This is
   the source of `CLAUDE.md`.)

8. **Specs.** `functional_spec.md` gains F10 for the hook, and F5's known limitation
   is rewritten to point at it rather than at an operator prompt.
   `architecture.md` gains the change-inventory row and a §1.3c.
   `implementation_plan.md` gains Phase 6, retires the operator-prompt checkbox and
   the open `SessionStart` decision, and adds `CREATE_STARTUP_SCRIPT=true` to the
   cloud `CONFIGURATION` block it tells the user to paste.

9. **Corrected measurements**, everywhere they appear (`functional_spec.md` F8/F9,
   `architecture.md`, `phase_plans/phase_5.md`, `project_overview.md`). The
   published figures were taken with a hot page cache and do not survive a
   snapshot-cold start:

   | Measurement | Published | Corrected |
   |---|---|---|
   | First `setup_startup.sh` in a session, warm tree present | 2.2 s | **22.9 s** (`real 22.890s, user 3.495s, sys 5.398s`) |
   | Same, warm tree disabled | — | **32.3 s** |
   | What the warm tree is worth | ~20 s implied | **9.4 s** |
   | `cp -al` of the tree | 0.54 s | 0.54 s **hot**; a cold-start seed is part of the 22.9 s |
   | Re-run inside one session | 5.9 s / 2.2 s | ~2 s, and that is the hot number |

   Under 9 s of that 22.9 s is CPU, so it is disk-bound; roughly 16 s of it is
   `npm install` reporting `up to date` while stat-ing ~46,000 files. The user has
   decided to keep the warm tree at 9.4 s — the point of the correction is to state
   the trade honestly, not to reopen it.

## Tests

Shell, JSON and docs, so no unit tests: verification is behavioral and every case
is executed. All of it runs against a temp `HOME`/`CLAUDE_CONFIG_DIR` and a temp
`KILN_VM_SETUP_DIR`, so the session's real `~/.claude/settings.json` is never
touched.

- **Merge into a file with existing keys**: `enableAllProjectMcpServers` and an
  unrelated top-level key survive verbatim; `hooks.SessionStart` gains exactly one
  entry.
- **Idempotency**: two runs produce exactly one `SessionStart` entry for the shim.
- **`settings.json` does not exist**: the file (and its directory) are created with
  just the hook.
- **Invalid JSON**: the file is left byte-identical, the run warns, and the exit
  code is still 0.
- **A pre-existing unrelated `SessionStart` hook**: it survives, and the Kiln entry
  is appended after it.
- **`hooks` present but of the wrong type** (e.g. a string): refuse, file unchanged.
- **Shim guard, non-Kiln directory**: exits 0 silently, runs nothing.
- **Shim guard, Kiln checkout**: runs `setup_startup.sh`, and from a subdirectory
  too.
- **Shim after a `KILN_VM_SETUP_DIR` move**: the stale entry is replaced, not
  duplicated.
- **Default off**: `setup_env.sh` without the flag writes no shim and does not read
  or write `settings.json`.
- **`--create-startup-script` with no checkout**: the shim and the settings entry
  are both written, which is the cloud environment-build case.
- **The generated settings file parses as JSON** and its hook entry matches the
  shape Claude Code's own schema accepts (`matcher`, `type`, `command`, `timeout`,
  `statusMessage`).
- **Non-ASCII in an unrelated setting** (`"échoué → naïve ✅ 日本語"`) comes back
  byte-identical, not escaped.
- **The marker never over-reports**: installed → the shim path; a refused
  registration → `registration_failed` even though the shim is on disk; a later run
  without the flag → the previous answer carried forward; never attempted → `none`.
- **Output cap**: a `setup_startup.sh` emitting ~335 KB is reduced to under 4 KB
  with both the first lines and the last lines — including the line carrying the
  actual reason — intact, and normal output passes through untouched.
- **Relative and non-existent `CLAUDE_PROJECT_DIR`**: resolved to an absolute path
  first, so a relative one still finds the checkout; a non-existent one falls back
  to `$PWD`; neither can spin the walk.
- **End-to-end, with the real CLI**: a session started with an isolated
  `HOME`/`CLAUDE_CONFIG_DIR` carrying the installed hook plus a `--settings` file
  carrying a second `SessionStart` hook runs **both** — the evidence that the
  launcher's git-identity hook is not displaced. Re-run after the matcher was
  added, to confirm a `startup` session still matches.
- `uv run ./checks.sh --agent-mode` green, suite still 6369 passed / 10020 skipped,
  and `git status --porcelain` showing only the intended edits.
