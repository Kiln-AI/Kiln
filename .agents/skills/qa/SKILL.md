---
name: qa
description: Multi-agent, browser-driven QA pass over a branch or PR — scope it, plan it, fan out one subagent per testing area in its own isolated sandbox, compile a severity-ranked markdown report. Use for an "E2E test", "QA pass", "manual test", or "bug bash" request — broader than driving the UI to check one fix (see `playwright`) or reviewing a diff (see `code-review`).
---

# QA: manual E2E testing over a branch

Driving Kiln's real UI, as a user would, to find what's broken — not code review, not the
automated Playwright suite. Read the `playwright` skill's `SKILL.md` and
`references/driving_the_ui.md` before doing anything here: this skill is the process wrapper
around it, and doesn't repeat its command-level mechanics or locator gotchas.

**This skill finds and documents issues. It does not fix them.** Note exceptions and hand
back a findings report, same posture as `kiln-prerelease-check`.

## When to use this vs. something else

- **Automated regression suite** (`npm run tests:e2e`) — a separate, already-existing thing
  this skill has nothing to do with running or maintaining.
- **The `playwright` skill** — the tooling this skill drives (dev sandbox, browser commands,
  screenshots). Read it as part of doing QA here; it also stands alone for a coding agent that
  just wants to check its own fix rendered correctly. That skill is the tooling; this skill is
  the pass that uses it.
- **This skill** — a QA person's pass over a bigger feature set, not one fix: real UI,
  end-to-end, looking for bugs, string issues, and inconsistencies across a set of screens or
  flows big enough that one person clicking through it alone would eat a day. Reach for it on
  an "E2E test", "QA pass", "manual test", or "bug bash" request.
- **Line-by-line review of a diff** — `code-review`, for reading code rather than clicking
  through the running app.

## Process

### 1. Get oriented, then confirm scope

Before touching a browser: if the invocation already tells you what to test and where to
focus, verify it against reality (see the cutoff-date check below) and move to planning. If
it doesn't — a bare "QA this branch" — browse for context first, then ask; don't guess at
scope or silently default to "test everything":

- Look around before asking anything: current branch/PR and its base, `git log --oneline` (and
  a diff against the likely base) to see what's actually there, any obviously-relevant
  `specs/projects/*` docs, any linked runbook or checklist. Show up to the question with real
  options, not a blank one.
- Then ask the user directly what to test and where to focus — a feature area, a date cutoff
  ("since the last bug bash"), a specific PR, a merge boundary. A branch big enough to need
  this skill is usually too big to cover exhaustively in one pass; let the user say what
  matters most rather than assuming "everything."
- If the user gives a cutoff date, verify it rather than trust it — check when the relevant
  commits actually landed. In one run, a "post-bug-bash polish" lane turned up commits that
  mostly predated the stated bug bash; that only surfaced because the dates were checked
  against `git log`, not assumed from the ask.
- If the user points at an existing manual-test doc — a runbook, a checklist, an Artifact link
  from another agent — fetch and read it in full before planning. Don't re-derive acceptance
  criteria that already exist; treat that doc as one of your lanes, executed close to verbatim.
- Skim `specs/projects/*/project_overview.md` and `functional_spec.md` for anything touched by
  the branch. These turn "click around and see if it feels right" into an actual checklist —
  named UI copy, specific modal behavior, specific field-level expectations — worth far more
  than generic exploration.

### 2. Write a plan, get approval before spending anything

Group the surface into independent testing lanes — split along feature/product seams, not
file count, so each lane can run without stepping on another's data or screens. Roughly
4–8 lanes is typical; fewer for a small change, more only if the user asks for broader
coverage.

**Do not launch subagents until the user approves the plan.** A run like this is expensive —
many tool calls, long-running agents, real wall-clock time — and the user may want to fold
lanes together, drop one, or hand you a specific runbook to fold in before you start. If the
user changes the plan mid-flight (adds a lane, removes one, points you at a doc), restate the
updated plan before proceeding; don't just silently absorb it and launch.

### 3. Launch one subagent per lane, isolated

See **Isolating parallel lanes** below for the mechanics. Launch all lanes' subagents in the
same response (multiple tool calls, one message) so they actually run in parallel, in the
background — don't await one before starting the next.

**Model:** run lane subagents on a mid-tier model — Sonnet, if the parent session is on
Anthropic — not the top-tier model the parent may be using. QA lanes are long, high-volume,
mechanical (drive the UI, read files, compare against a spec) rather than deep-reasoning work,
and a run this size burns a lot of tokens across 4–8 multi-hour agents. Pass this explicitly
via the `model` param on each `Agent` call rather than leaving it to inherit the parent's
model.

### 4. Compile the report

- As each lane reports back, give the user a short live update (1–3 sentences: verdict +
  headline finding) rather than staying silent until everything lands — these runs take a
  long time and the user is watching progress, not just waiting for a final dump.
- Cross-reference findings across lanes once everyone's back. Two lanes independently hitting
  the same gap (e.g. "no edit path for a saved config") is worth calling out as corroborated,
  not just deduped away.
- Severity-tag every finding (blocker / major / minor / cosmetic) and tag whether it's
  actually inside the stated focus window — something can be real and broken while predating
  the window you were asked to focus on; say which.
- Clean up every sandbox you spun up (see below) before declaring done — leftover
  `.agent_dev_home_*` directories are untracked scratch state that will trip a repo's
  untracked-files hook.
- Write the report as **markdown**, not an HTML artifact — this is an internal engineering
  report, not a designed deliverable. Group by severity, not by lane, since a reader triaging
  wants "what do I fix first," not "what did lane 3 find." Send it as a file if it's long
  enough that pasting it into chat would bury the headline.

## Isolating parallel lanes

Two independent axes of isolation, and both matter for every lane:

### Dev server isolation — its own backend, frontend, and project data

```bash
export KILN_DEV_FRONTEND_PORT=<unique port>
export KILN_DEV_BACKEND_PORT=<unique port>
export KILN_DEV_HOME=/home/user/Kiln/app/web_ui/.agent_dev_home_<lane>
bash .agents/scripts/playwright_server.sh start
```

Each lane gets its own backend + frontend pair, freshly seeded from the same committed
fixture, writing into its own file-backed project directory. Without this, concurrent lanes
share one on-disk Kiln project: two agents creating specs/evals at once can race, and one
lane's test data pollutes another lane's counts and filters.

For a lane that must intentionally corrupt a file on disk (testing error handling / partial
load), it must use its own **fresh scratch project**, not the seeded fixture — tell the
subagent explicitly not to touch `.agents/playwright_project`, and to keep the corrupted
sandbox around until findings are confirmed rather than deleting it mid-investigation.

### Browser session isolation — named `playwright-cli` sessions

`playwright-cli` supports named sessions via `-s=<name>` — each is a fully separate browser
context: own cookies, localStorage, sessionStorage, open tabs. Give every lane a unique
session name and instruct its subagent to pass `-s=<name>` on **every single**
`playwright-cli` call for that lane's entire run. Omit it even once and that call silently
falls back to the shared default session, where two lanes fight over the same window and
clobber each other's navigation mid-test.

The two axes are independent — set both, every time:

| | own dev server | shared dev server |
|---|---|---|
| **own `-s=` session** | fully isolated ✅ | data races between lanes |
| **shared/default session** | navigation races between lanes | both |

Cleanup per lane, once its findings are captured:

```bash
playwright-cli -s=<lane> close
bash .agents/scripts/playwright_server.sh stop   # (with that lane's KILN_DEV_* env still set)
rm -rf app/web_ui/.agent_dev_home_<lane>
```

## Briefing each lane's subagent

A lane subagent starts with none of your context — brief it like a self-contained assignment:

- The branch/scope, and *why* this lane is risky or worth a dedicated pass (what changed,
  what it interacts with) — not just a list of screens to click.
- The exact isolation env-var block and its unique session name, with an explicit instruction
  to use `-s=<name>` on every call.
- Pointer to the `playwright` skill for command mechanics and Kiln-specific locator traps
  (never trust the first rendered frame; never redirect `playwright-cli` output to
  `/dev/null`; DaisyUI dropdowns/collapsed sections hiding fields from `find`/`snapshot`).
- Concrete files to read first — the actual diff/component list for this lane, not a vibe.
  Testing against the real change beats testing against a guess of what the change probably
  did.
- **Find and document only** — no source edits. State the one exception plainly when it
  applies: intentionally corrupting a file in its own scratch project to test error handling.
- Whether a live model/provider is available in this sandbox (usually not, by default — see
  below) so it knows which blocked paths are expected, not bugs.
- The report shape you want back: one entry per finding, with area, severity, concrete repro
  steps, expected vs. actual, a file:line reference where relevant, and whether the finding
  falls inside the stated focus window (`git log --oneline -- <file>` settles this when
  unsure).
- An instruction to clean up its own server/session/scratch directory when done.

## No LLM provider by default

The seeded dev sandbox has no API key, so anything needing a live model call — LLM-judge
scoring, synthetic data generation, Copilot-backed flows, provider-gated features — will fail
or gate off cleanly. Tell every lane this up front so those paths get reported as
expected/partial rather than bugs, while the lane still verifies everything reachable around
the gate: form validation, error messages, degrade-gracefully behavior, whatever UI exists
before the live call would happen.

If a live model call is actually essential to a lane's coverage — the feature can't be
meaningfully verified any other way — don't just skip it. Ask the user for an OpenRouter API
key with a small max-spend limit, scoped to this test run, and connect it through the app's
own Settings UI (not a raw env var) so it behaves exactly like a real user's connected
provider. OpenRouter covers most models through one key; only ask for a different provider's
key if the thing under test is specific to that provider.

## Report shape

Write it in **markdown**, not an HTML artifact. Lead with anything blocker-severity in plain
language before the supporting detail. Group the final write-up by severity, not by lane. For
each finding: one-line summary, severity, area, concrete repro, expected vs. actual, file:line,
and whether it's actually inside the requested focus window. Close with a short overall
verdict and a recommendation (fix before merge vs. a product decision vs. fine to ship as-is).
