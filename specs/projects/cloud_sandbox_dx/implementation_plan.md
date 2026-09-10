---
status: complete
---

# Implementation Plan: Cloud Sandbox Developer Experience

## Phases

- [x] Phase 1: uv floor and Python 3.13 pin — `required-version` in
      `pyproject.toml`, `.python-version` in `.gitignore`. Small, independent, and
      the foundation everything else assumes.
- [x] Phase 2: `setup_env.sh` rewrite — `CONFIGURATION` block, flags, uv version
      gate, Python 3.13, parallel `uv sync --frozen --all-packages` + `npm ci`,
      agent config, `--human` extras, `--best-effort`.
- [x] Phase 2b: `setup_startup.sh` — per-session hard-dependency gate plus
      `uv sync` / `npm install` top-up. Added after research §12 showed the setup
      script runs once per environment and is then snapshotted and skipped, so
      nothing repo-aware runs per session.
- [x] Phase 3: `conftest.py` deferred litellm import, including the log-path
      verification called out in the architecture.
- [x] Phase 4: `AGENTS.md` environment-setup section.
- [x] Phase 5: warm `node_modules` (F9) — `WARM_CACHE` in the repo's own
      `setup_env.sh`, the `.setup_for_kiln_repo_v1` provisioning marker, the
      hardlink seed and container gate in `setup_startup.sh`, and the doc updates
      those force. Added after a live sandbox showed cache warming fixed the Python
      half outright (14.67 s → 428 ms) and barely touched the Node half (24 s →
      21 s), because npm copies out of its cache where uv hardlinks. End to end the
      warm tree is worth **9.4 s** of a snapshot-cold session (32.3 s → 22.9 s);
      the per-command figures above are hot-cache numbers.
- [x] Phase 6: the `SessionStart` hook (F10) — `CREATE_STARTUP_SCRIPT` /
      `--create-startup-script` in `setup_env.sh`, the hook shim in `$VM_SETUP_DIR`,
      and its idempotent merge into the user-level `~/.claude/settings.json`, plus
      the measurement corrections above. This closes F5's circular bootstrap, which
      the plan previously carried as an operator-side prompt and an open decision —
      both retired below.

Phases 2 and 3 are independent and can be reviewed separately. Phase 4 depends on
Phases 2 and 2b being settled, since it documents that interface. Phase 5 extends
both scripts and re-touches the same docs, so it comes late. Phase 6 builds on
Phase 5's `$VM_SETUP_DIR` and marker, so it comes last.

## Validation

Each phase ends with `uv run ./checks.sh --agent-mode` green and
`git status --porcelain` empty.

Final validation for the project must happen in a **fresh** cloud sandbox against
the nine success criteria in the functional spec. Re-running in an already-repaired
session proves nothing — the current session has had uv upgraded and the venv
rebuilt on Python 3.13 by hand during research.

## Environment-side work (not code, tracked here so it isn't lost)

Outside the repo, in the Claude Code cloud environment configuration:

- [ ] Setup script set to the **contents** of `.config/utils/setup_env.sh`, with
      `UPGRADE_TOOLS=true`, `BEST_EFFORT=true`, `WARM_CACHE=true` and
      `CREATE_STARTUP_SCRIPT=true` in its `CONFIGURATION` block (functional spec,
      "Environment-side changes"). Not a wrapper that calls the repo copy — see
      research §12 for why that cannot work.

      Re-paste after Phase 5: `WARM_CACHE` is what warms the VM's caches and leaves
      the `node_modules` tree that `setup_startup.sh` hardlinks, and until the paste
      happens the marker is missing, so every session prints the "this VM was not
      set up for Kiln" notice and skips the hardlink.

      Re-paste again after Phase 6: `CREATE_STARTUP_SCRIPT` is what installs the
      `SessionStart` hook, and it is the item below that it retires.
- [ ] `UV_NATIVE_TLS` — **no action available; leave it alone.** The variable is
      deprecated and uv warns on every invocation, but Claude Code sets it in the
      image, so the user cannot remove it from the environment's variables.

      Overriding it with a falsy value does **not** help. Measured on uv 0.12.5,
      the warning depends only on the variable being *present and parseable*, not
      on its value:

      | `UV_NATIVE_TLS` | result of `uv run` |
      |---|---|
      | unset | silent — the only quiet case |
      | `false` / `0` | warns |
      | `true` / `1` | warns |
      | empty string | **hard error** — uv refuses to run: "expected a boolish value" |

      So `UV_NATIVE_TLS=false` buys nothing, and `UV_NATIVE_TLS=` (empty) would
      break every uv invocation in the sandbox. The warning is cosmetic — one
      stderr line per uv call, no behavioral effect once `UV_SYSTEM_CERTS` is set —
      and is best left until either Claude Code stops setting it or uv drops it.
- [ ] `enableAllProjectMcpServers: true` in user-level `~/.claude/settings.json`,
      so the project `.mcp.json` is trusted. Nothing repo-side can do this.
- [x] ~~**Name `setup_startup.sh` in the operator-side prompt or environment
      instructions.**~~ **Retired by Phase 6 — no operator prompt is needed.**
      `CREATE_STARTUP_SCRIPT=true` makes the setup script install a `SessionStart`
      hook that runs `setup_startup.sh` before the agent's first turn, so the
      circular bootstrap closes inside this project. Nothing to write by hand; the
      only action is the re-paste in the first item.
- [x] Add `UV_SYSTEM_CERTS` to the environment variables. Done — verified present
      in this session. Note this **added** the modern variable rather than
      replacing the deprecated one, since the image sets `UV_NATIVE_TLS` and the
      environment config cannot unset it; both are live. See the item above.

## Settled: the `SessionStart` hook (was an open decision)

Resolved in Phase 6, and the decision it was framed as never had to be taken. The
question was whether to track a `.claude/settings.json` in the repo, which would
have made part of a generated, disposable directory into source. It does not,
because the hook does not have to come from the repo at all:

- **User-level hooks fire in cloud sandboxes.** `~/.claude/settings.json` is read
  in these sessions (it already carries `enableAllProjectMcpServers`), `~/.claude/`
  is on the snapshotted filesystem, and the environment's own hooks —
  `session-start-git-identity.sh` and the `Stop` git check, both registered in
  `~/.claude/launcher-settings.json` — demonstrably run.
- **So the VM setup script installs it**, with `--create-startup-script`. No repo
  file, no tracked `.claude/`, no convention changed.
- **Hooks merge across settings sources rather than override**, so the entry does
  not displace the launcher's git-identity hook. Verified twice: a live session in
  which a `settings.json` hook and a `--settings` hook both fired, and the merge
  rule in Claude Code itself (arrays are concatenated and de-duplicated).

The residual cost is honest and accepted: session start is ~23 s longer on a
snapshot-cold VM, and `setup_startup.sh` now runs in sessions where no agent asked
for it. See F10.

## Follow-up, was blocked on upstream

- [x] Set a floor in `.agents/mcp.json`: `--from "hooks-mcp>=0.2.5"`. Not a pin — a
      floor — because `uvx` reuses cached tool environments and could otherwise keep
      serving the broken 0.2.4 + mcp 2.0 pair. Unblocked by the 0.2.5 release;
      verified by driving the configured command over stdio (`initialize` plus
      `tools/list` return all 17 configured tools).
