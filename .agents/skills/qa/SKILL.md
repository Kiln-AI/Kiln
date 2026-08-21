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
- **The `playwright` skill** — describes the tooling required for this skill (dev sandbox,
  browser commands, screenshots). Read it as part of doing QA here; it also stands alone for a
  coding agent that just wants to check its own fix rendered correctly. That skill is the
  tooling; this skill is the pass that uses it.
- **This skill** — a virtual QA team mate, making a pass over a bigger feature set, not one
  fix: real UI, end-to-end, looking for bugs, string issues, and inconsistencies across a set
  of screens or flows big enough that one person clicking through it alone would eat a day.
  Reach for it on an "E2E test", "QA pass", "manual test", or "bug bash" request.
- **Line-by-line review of a diff** — `code-review`, for reading code rather than clicking
  through the running app.

## Process

### 1. Ask scope, then get oriented

If the invocation doesn't already say what to test and where to focus, ask the user directly
— don't guess, and don't pile the guesswork onto them either by making them spell out every
detail unprompted. **The whole branch/PR is the default, most common answer**: everything new
on it is fair game for a QA pass unless the user narrows it. Name the less-common alternatives
so they're easy to pick if that's what's wanted — a date cutoff ("since the last release"), a
specific PR, a single feature area — but expect "the whole thing" most of the time.

Once scope is set, get oriented before drafting a plan: current branch/PR and its base,
`git log --oneline` (and a diff against the base) to see what actually landed, any
obviously-relevant `specs/projects/*/project_overview.md` or `functional_spec.md` docs. These
turn "click around and see if it feels right" into an actual checklist — named UI copy,
specific modal behavior, specific field-level expectations — worth far more than generic
exploration.

If the user gave a date cutoff, verify it rather than trust it at face value — check when the
relevant commits actually landed before treating that date as the real boundary.

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
- Clean up every sandbox you spun up (see below) before declaring done — leftover directories
  under `.agent_qa_sandboxes/` are untracked scratch state that will trip a repo's
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
export KILN_DEV_HOME="$(git rev-parse --show-toplevel)/app/web_ui/.agent_qa_sandboxes/<lane>"
bash .agents/scripts/playwright_server.sh start
```

Repo-root-relative, not a hardcoded absolute path — a path like `/home/user/Kiln/...` copied
verbatim breaks on any checkout that isn't at that exact location. And every lane's directory
lives under one parent (`.agent_qa_sandboxes/`), not scattered as loose
`.agent_dev_home_<lane>` siblings of the real dev sandbox — keeps a multi-lane run from
littering `app/web_ui/` with a pile of unrelated hidden folders.

Each lane gets its own backend + frontend pair, freshly seeded from the same committed
fixture, writing into its own file-backed project directory. Without this, concurrent lanes
share one on-disk Kiln project: two agents creating specs/evals at once can race, and one
lane's test data pollutes another lane's counts and filters.

`start` only seeds a project into `KILN_DEV_HOME` the *first* time it sees that directory (it
checks for a `.playwright_seed` stamp file and skips seeding if one's already there) — it does
not refresh an existing one. If a lane's directory could already exist from an earlier run
(resuming a QA pass, reusing a lane name), use `reset` instead of `start` to guarantee a clean
fixture rather than whatever that directory happened to have in it.

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
rm -rf app/web_ui/.agent_qa_sandboxes/<lane>
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
- Whether a live model/provider is available in this sandbox (check `start`'s output — see
  below) so it knows which blocked paths are expected and which are bugs. When one *is*
  connected, pass on the spending rules verbatim: GPT-5.6 Luna by default, smallest possible
  runs, stop on a 402/429.
- The report shape you want back: one entry per finding, with area, severity, concrete repro
  steps, expected vs. actual, a file:line reference where relevant, and whether the finding
  falls inside the stated focus window (`git log --oneline -- <file>` settles this when
  unsure).
- An instruction to clean up its own server/session/scratch directory when done.

## Whether an LLM provider is connected — check, don't assume

Some environments set `OPENROUTER_QA_KEY`, and where it's set, seeding a sandbox writes it
into that sandbox's settings and the app comes up with OpenRouter connected — live model
calls work, exactly as they would for a user who connected a provider in Settings.
`playwright_server.sh start` says so in its output when that's the case. **Check the output
of your own `start` before planning around it**, and tell every lane which world it's in.

### When a key is connected

It's a real key on a hard, low spending limit, shared by every lane in the run. A lane that
burns it leaves the rest of the run with nothing, so the budget is a shared resource to
protect, not an allowance to use up:

- **Default to GPT-5.6 Luna** (`openai/gpt-5.6-luna`) for anything where the model isn't the
  point — which is nearly everything in a QA pass. Use a different model only when the thing
  under test is that model's behavior.
- **Smallest run that answers the question.** One sample, one eval row, one search query. A
  QA pass proves the flow works; it doesn't need a populated dataset.
- **Never point a paid test suite at it.** `pytest --runpaid` and `--runprerelease` read
  `OPENROUTER_API_KEY`, deliberately a different variable — don't bridge them.
- **A 402 or 429 means the budget is gone.** Stop, report it as a run-level note, and don't
  retry — a retry loop is how one lane ends the whole pass.

Say all of this in each lane's brief. The limit is what actually stops a runaway; the
guidance is what keeps the run from reaching it.

### When no key is connected

Anything needing a live model call — LLM-judge scoring, synthetic data generation,
Copilot-backed flows, provider-gated features — will fail or gate off. Tell every lane this up
front, but keep the exemption narrow: only the failure that's *directly caused by the missing
provider itself* (the call can't be made, so that specific path stops) is expected/partial,
not a bug. Everything else at that same gate is still in scope and still gets reported as a
real finding — a crash instead of a clean error, a gate that fires at the wrong time or not at
all, a missing/garbled error message, a "degrade gracefully" path that doesn't. The lane
should verify all of that reachable-before-the-call behavior, not wave the whole area through
because a key was missing somewhere downstream of it.

If a live model call is actually essential to a lane's coverage — the feature can't be
meaningfully verified any other way — don't just skip it. Ask the user for an OpenRouter API
key with a small max-spend limit, scoped to this test run, and connect it through the app's
own Settings UI (not a raw env var) so it behaves exactly like a real user's connected
provider. OpenRouter covers most models through one key; only ask for a different provider's
key if the thing under test is specific to that provider. The same spending rules above apply
to a key given this way, and more so — it's the user's, given for one run.

## Report shape

Write it in **markdown**, not an HTML artifact. Lead with anything blocker-severity in plain
language before the supporting detail. Group the final write-up by severity, not by lane. For
each finding: one-line summary, severity, area, concrete repro, expected vs. actual, file:line,
and whether it's actually inside the requested focus window. Close with a short overall
verdict and a recommendation (fix before merge vs. a product decision vs. fine to ship as-is).
