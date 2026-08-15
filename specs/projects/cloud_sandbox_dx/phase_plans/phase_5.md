---
status: complete
---

# Phase 5: Warm `node_modules`, a Provisioning Marker, and a Container Gate

## Overview

Phases 2 and 2b left one measured cost unpaid. Warming the global caches from a
throwaway clone before the VM snapshot is taken fixed the Python half outright —
`uv sync` in a fresh session went from `Prepared 182 packages in 14.67s` to
`Prepared 3 packages in 428ms`, with the ~300 MB download, the `together` git
fetch and the `google-crc32c` sdist build all gone; only the three local workspace
packages still build, which is irreducible because they come from the checkout's
own source.

The Node half barely moved: 24 s → 21 s. A warm `~/.npm` saves the download, but
npm **copies** out of its cache where uv **hardlinks**, so materializing 748
packages into an empty `node_modules` still costs ~21 s. The fix is to skip the
materialization entirely: keep the pristine `node_modules` tree the warm-up run
already built, outside the repo so it survives into the VM snapshot, and
hardlink-copy it into the session's checkout. Measured on this machine: `cp -al`
of the 601 MB tree takes **0.54 s** and shares inodes, and `/opt` and `/home/user`
are the same device, so the link is possible.

Three supporting pieces come with it:

- The `WARM_CACHE` flag that does the warm-up currently exists **only** in the copy
  the user pastes into the cloud environment dialog. That breaks this project's
  core contract (F1): the pasted script is the repo file with only its
  `CONFIGURATION` block edited. Landing the flag here restores it.
- A **provisioning marker** outside the repo, so `setup_startup.sh` can tell a VM
  built by `setup_env.sh` from one that never ran it. Absent marker means the
  warm tree — if any — has unknown provenance and must not be linked into a
  checkout.
- A **container gate** on `setup_startup.sh`. It exists for fresh containers.
  Locally the environment is already set up and shared, and a script that seeds
  `node_modules` from a machine-global tree has no business running there.

## Steps

1. **`.config/utils/setup_env.sh` — `WARM_CACHE` flag.** Add
   `WARM_CACHE=false` to the `CONFIGURATION` block (with the comment naming the
   cloud value), a `--warm-cache` flag in the parser, and a line in `usage`.
   Default false, so local runs and every other repo using the environment are
   unaffected.

2. **`setup_env.sh` — VM setup directory constants**, next to `UV_MIN`:

   ```bash
   VM_SETUP_DIR="${KILN_VM_SETUP_DIR:-/opt/kiln-vm-setup}"
   VM_SETUP_MARKER="$VM_SETUP_DIR/.setup_for_kiln_repo_v1"
   WARM_NODE_MODULES="$VM_SETUP_DIR/node_modules"
   KILN_REPO_URL="${KILN_REPO_URL:-https://github.com/Kiln-AI/Kiln.git}"
   ```

   One directory holds both the marker and the warm tree. The `_v1` in the marker
   name is the contract version: bump it when what setup provides changes
   incompatibly, so VMs provisioned by an older script are correctly reported as
   not set up. `KILN_VM_SETUP_DIR` and `KILN_REPO_URL` are overridable so the
   behavior is testable without writing to `/opt` or cloning over the network.

3. **`setup_env.sh` — `warm_from_throwaway_clone`.** Runs only with
   `WARM_CACHE=true` **and** no checkout — the cloud environment-build case. It
   clones Kiln shallowly into `$VM_SETUP_DIR`, writes `.python-version` into the
   clone first (so the cached wheels match the interpreter the sessions will use),
   runs `uv sync --frozen --all-packages` and `npm ci` in it (in parallel, same
   `wait`-both pattern as §1.4), then `mv`s the clone's `node_modules` to
   `$WARM_NODE_MODULES` and deletes the clone. Cloning *inside* `$VM_SETUP_DIR`
   keeps the tree on one device, so the `mv` is a rename rather than a 601 MB copy.

   Failures here are **warnings, not `fail`s**: the warm-up is an optimization, and
   marking the run failed would flip the closing line to "Resolve the errors above"
   for a machine whose uv and Python are fine. `setup_startup.sh` re-checks
   everything that matters per session anyway.

4. **`setup_env.sh` — `write_vm_setup_marker`.** Writes `$VM_SETUP_MARKER` with
   `setup_version`, a timestamp, the uv version, the Python pin, the warm tree path,
   whether a tree is present, the commit it was built from, and whether this run
   made it — enough to diagnose a stale or wrong VM later. Called on every run, both
   the checkout and the no-checkout path. If the directory cannot be created (a
   local machine where `/opt` is not writable), print one low-key note and continue:
   the marker only means anything on a VM.

   The tree fields describe state, not this run's history. A re-run without
   `--warm-cache` — the repair command `AGENTS.md` gives — makes no tree while the
   existing one survives and keeps seeding sessions, so `previous_marker_value`
   carries the prior commit forward rather than overwriting it with `none`.

5. **`.config/utils/setup_startup.sh` — container gate.** After argument parsing,
   before project-root discovery. Treat `CLAUDE_CODE_REMOTE` (set to `true` by
   Claude Code in cloud sessions) or `IS_CONTAINERIZED` (the manual escape hatch)
   as set when non-empty and not `false`/`0`. With neither, print
   `Not running in a VM/container, will not run custom setup.` plus what to do
   instead, and **exit 0** — a normal outcome, not an error.

6. **`setup_startup.sh` — marker check.** Same constants as step 2. After project
   root discovery, before the hard-dependency gate, so it frames the failures that
   are likely to follow. When the marker is absent, print a prominent block saying
   the VM setup script should have run and did not, and set a flag that disables the
   hardlink. Everything else proceeds — a missing marker is a warning, not fatal.

7. **`setup_startup.sh` — seed `node_modules` from the warm tree.** Immediately
   before the sync, and only when: the checkout has no `node_modules`, the marker
   was present, and `$WARM_NODE_MODULES` exists. `seed_warm_node_modules` does
   `cp -al` into a staging directory beside the target, unshares the regular files
   at the root of staging, and only then renames it into place — so `node_modules`
   never exists in a partial *or* fully shared state. Staging must sit on the
   destination filesystem or the `mv` would turn into a 601 MB copy and lose the
   links. Any failure — cross-device image, `cp -al` unsupported, a failed unshare —
   removes the staging directory, prints a capped note, and falls through to the
   plain `npm install` that happens today. Capped because a cross-device tree fails
   once per file: 46,436 lines, so three and a count, from a temp file rather than a
   shell variable.

   Staging is per-PID, and the leak that creates — a killed run's directory under a
   name nothing reuses — is reclaimed by an age-based sweep of anything older than
   an hour, run unconditionally so it is not skipped once `node_modules` exists. A
   shared staging name was tried and reverted: racing two seeds on one name
   corrupted `node_modules` in 57 of 60 runs, silently.

8. **Documentation.** `AGENTS.md` and `CONTRIBUTING.md` must stop implying that
   `setup_startup.sh` syncs dependencies everywhere, since outside a container it is
   now a no-op, and must say what local contributors do instead. `functional_spec.md`
   F8 gains the gate, the marker and the seeding, and its "Environment-side changes"
   config block gains `WARM_CACHE=true`. `architecture.md` §1 and §1B gain the same,
   plus the change-inventory rows. `implementation_plan.md` gains Phase 5 and the
   updated cloud `CONFIGURATION` block. Phases 2 and 2b get a one-line pointer that
   Phase 5 extended them, so a reader of those plans is not misled.

## Tests

Shell and docs, so no unit tests — verification is behavioral, and every case is
executed rather than reasoned about. `KILN_VM_SETUP_DIR` and `KILN_REPO_URL` make
each case runnable without touching `/opt` or the network.

- **Container gate, neither variable set**: prints the "not running in a
  VM/container" line and exits 0 without touching the checkout.
- **Container gate, `CLAUDE_CODE_REMOTE=false` / `0` / empty**: same, treated as
  unset.
- **Container gate, `IS_CONTAINERIZED=true` with `CLAUDE_CODE_REMOTE` unset**: runs
  the full startup.
- **Marker absent**: prominent warning, no hardlink attempted even when a warm tree
  exists, and the run still exits 0 with the normal `Ready.` line.
- **Marker present, warm tree absent**: no warning, no seeding, plain `npm install`.
- **Marker present, warm tree present, `node_modules` missing**: the tree is seeded,
  and `ls -i` proves the checkout's files and the warm tree's files are the **same
  inode**, not a copy.
- **Marker present, warm tree on another filesystem** (`/dev/shm`): `cp -al` fails
  with a cross-device error, the note is printed, no staging directory is left
  behind, and `npm install` populates `node_modules` as it does today.
- **`node_modules` already present**: no seeding, unchanged behavior.
- **In-place-write risk**: with the checkout seeded from a warm tree, record every
  file's inode, size and mtime in the warm tree, run `npm install` and a web build,
  and re-compare — proving whether npm and the build tooling replace files (safe) or
  edit them in place (which would mutate the snapshot's baseline).
- **`setup_env.sh --warm-cache` with no checkout**: clones, syncs, and leaves both
  the marker and a populated `node_modules` under `$KILN_VM_SETUP_DIR`, with the
  clone deleted.
- **`setup_env.sh` with a checkout**: writes the marker, records
  `warm_node_modules_created_this_run=false`, and does not clone.
- **`setup_env.sh` re-run without `--warm-cache` over an existing warm tree**: the
  marker still reports the tree as present and keeps its original commit.
- **Cross-device fallback output is bounded**: three lines and a count, not one line
  per file.
- **Unshare failure**: the seed fails, the staging tree is removed, and the run
  falls back to `npm install` rather than reporting a seed that did not happen.
- **`IS_CONTAINERIZED=no`**: treated as unset.
- **Two seeds racing on one checkout**: 30 races against a 52,037-entry warm tree
  leave a correct `node_modules` every time and no staging behind, where a shared
  staging name corrupts it in 10 of 10.
- **Age sweep**: a two-hour-old `.node_modules.warm.*` is reclaimed on a run that
  skips seeding entirely; a fresh one is left alone.
- `uv run ./checks.sh --agent-mode` green, suite still 6369 passed / 10020 skipped,
  and `git status --porcelain` empty apart from the intended edits.
