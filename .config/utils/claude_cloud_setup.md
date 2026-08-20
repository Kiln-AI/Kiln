# Claude Cloud Setup for Kiln

Setting up a Claude Code cloud environment for this repo. One time, about five
minutes.

> **Team/Enterprise:** if an admin has already created a shared "Kiln"
> environment, skip to step 4 and pick it from the selector. Environments can be
> shared org-wide, so this only needs doing once for everyone.

## 1. Connect GitHub

At [claude.ai/code](https://claude.ai/code), authorize the Claude GitHub App if
you haven't already.

## 2. Create a cloud environment

Select the cloud icon in the row above the message box → **Add cloud
environment**. There is no settings page or direct URL for it.

- **Name:** `Kiln`
- **Network access:** **Custom**
  - **Allowed domains**, one per line:

    ```
    cdn.playwright.dev
    playwright.download.prss.microsoft.com
    ```

  - Check **Also include default list of common package managers**. That keeps
    the whole Trusted list: PyPI, npm, apt, and `raw.githubusercontent.com`,
    which the setup script fetches itself from.

The default **Trusted** policy is not enough on its own: the two domains above
are Playwright's CDN and its download fallback, and on Trusted they answer 403,
so the environment comes up without a browser. Everything else Kiln's setup
needs is in the default list.

## 3. Fill in two fields

**Environment variables:**

```
UV_SYSTEM_CERTS=true
```

The image sets the deprecated `UV_NATIVE_TLS` and the environment config cannot
unset it, so this **adds** its modern replacement rather than replacing it. Both
end up live. See "Things to know" below.

**Setup script:** paste the *entire contents* of
[`.config/utils/claude_code_vm_setup.sh`](claude_code_vm_setup.sh) into the
**Setup script** field.

That file is a wrapper, not the real setup: it fetches
[`setup_env.sh`](setup_env.sh) from `main` and runs it. The setup script field
holds a copy that nothing updates, and it runs at environment-build time before
any repo is checked out, so it cannot read the repo copy from disk. The wrapper
is small and changes almost never, so pasting it once is the last manual step —
`setup_env.sh` can then change freely.

## 4. Start a session

Pick the environment from the cloud icon, choose the Kiln repo, and go.

---

## What to expect

The **first** session in a new environment runs the setup script and then
snapshots the disk, which takes a few minutes — it warms the uv and npm caches
and installs ~800 MB of Playwright browsers. Every session after that starts
from the snapshot and skips it. The setup script runs again when you change it
or the allowed-domain list, and when the snapshot expires after roughly seven
days.

You don't need to run anything to prepare the checkout. A `SessionStart` hook
runs [`setup_startup.sh`](setup_startup.sh) before your first turn — it syncs
dependencies for your branch and writes the agent config (`CLAUDE.md`,
`.claude/skills/`, `.mcp.json`, all gitignored) — so `uv run`, `npm run` and
`pytest` just work. It adds roughly twenty seconds to session start, and about
two seconds if anything re-runs it later in the session. That's the trade for
not having to think about it.

## Checking it worked

Your first turn's context should end with something like:

```
Syncing dependencies for main...
Ready. Python 3.13, uv 0.12.5, agent config written.
```

On the first session in a fresh container it also says
`Seeded node_modules by hardlink from /opt/kiln-vm-setup/node_modules.` above
that; later runs in the same session already have `node_modules` and skip it.

What says it did *not* work:

- `! This VM was not set up for Kiln: /opt/kiln-vm-setup/... is missing.` — the
  setup script never ran, or ran an older version. Re-check step 3.
- any `✗` line — a uv below the minimum, a virtualenv on the wrong Python, a
  Python without tkinter — the environment build did not finish. Each of those
  names its own repair, and it is the same one: run it in-session with
  `bash .config/utils/setup_env.sh --upgrade-tools`.
- `! Playwright is not fully installed here` — the allowlist in step 2 is
  missing or wrong. Repair with
  `bash .config/utils/setup_env.sh --add-playwright`, and see
  [`.agents/USING_PLAYWRIGHT.md`](../../.agents/USING_PLAYWRIGHT.md).

You can re-run the whole check any time; it is cheap and idempotent:

```
bash .config/utils/setup_startup.sh
```

## Things to know

**`uv` prints a `UV_NATIVE_TLS is deprecated` warning on every command.** It is
cosmetic and cannot be removed — Claude Code sets the variable in the image, and
the warning depends only on it being present and parseable, not on its value. Do
not try to neutralize it in the environment variables: `UV_NATIVE_TLS=false`
still warns, and `UV_NATIVE_TLS=` (empty) makes uv refuse to run at all.

**A session can leave `app/web_ui/package-lock.json` modified.** The startup
script uses `npm install` rather than `npm ci`, because it is incremental and a
warm `node_modules` makes it near-free — but it rewrites the lockfile when the
lockfile and `package.json` disagree. It says so on stderr and names the file
when that happens; `git checkout -- app/web_ui/package-lock.json` if the change
wasn't yours.

## Testing a change to the setup

`KILN_SETUP_REF` overrides the ref the wrapper fetches `setup_env.sh` from, so a
branch's version can be tried without merging it. Set it in the pasted setup
script itself, above the rest:

```bash
KILN_SETUP_REF=my-branch
```

In the script rather than in the environment variables, for two reasons: the
variables are documented as reaching the *session*, not the build-time setup
script, and editing the setup script is one of the things that forces the
snapshot to rebuild — which is what makes the new setup actually run.
