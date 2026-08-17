---
status: draft
---

# Phase 2: Runs, ratings, and the small artifacts

## Overview

Phase 2 authors architecture.md's content groups 2 and 3 into the committed fixture:
the runs that make every dataset, comparison, and eval screen show something, and the
four small artifacts that hang off them (a saved prompt, a dataset split, an input
transform, and human feedback on a run).

Nothing in this phase is code. The diff should be JSON under
`.agents/playwright_project/` plus this plan. Everything is created by clicking through
the app at `http://localhost:6544` and captured with
`.agents/scripts/playwright_server.sh snapshot`.

Generation uses `deepseek/deepseek-v4-flash-0731` through OpenRouter, connected through
the UI so the key lands in the sandbox's gitignored `settings.yaml` — which `snapshot`
never reads. That property is the whole reason the key cannot reach the repo, so nothing
in this phase reads or writes settings by hand.

## Steps

Each numbered group ends in a `snapshot` and a `git diff` review, per architecture.md's
resumability rule. A lost session costs at most one group.

### 1. Connect OpenRouter through the UI

Settings → Providers → OpenRouter → paste key → Connect. Phase 1 left a placeholder
Custom API connected in *its* sandbox only; settings are never snapshotted, so a
freshly-seeded sandbox has no providers at all and OpenRouter is the only one this phase
adds. Nothing here reaches the fixture.

### 2. Run config A, and the bulk of the runs

Run the structured **Triage Ticket** task from `/run` with
`deepseek/deepseek-v4-flash-0731`, structured output mode `json_schema`. That first run
mints run config A. Then keep running with varied ticket inputs — different teams,
priorities, plans, and a couple that should escalate — until the structured task has
roughly a dozen runs.

Then run the plain-text **Draft Ticket Reply** task a handful of times, so the
unstructured screens have data too.

Target 15–20 runs total, weighted to the structured task.

### 3. Run config B on the structured task

Change a run option that forks the run config — a different prompt selection (e.g. the
"Chain of Thought" / thinking prompt rather than Basic) at the same model — and run the
structured task several more times. Comparison and eval screens need two run configs on
one task to be worth opening.

### 4. Ratings, spread on purpose

From the Dataset screen, rate runs by opening each and using the rating control:

- Several **high** (4–5 overall, with the per-requirement ratings the structured task
  offers).
- A couple **low** (1–2), on runs whose output really is wrong or thin.
- **Several left unrated.** This is content, not an omission: the dataset filters and the
  eval split screens have nothing to show without unrated rows.

### 5. A repair

Pick one low-rated structured run, use the repair flow to supply a corrected output, and
save it. At least one run in the fixture must carry `repaired_output` and a repair
instruction.

### 6. Feedback on a run

Leave human feedback (the free-text note on a run) on at least one run.

### 7. Prompt, split, transform

- **Saved prompt** — from the Prompts screen, save a custom prompt for the structured
  task.
- **Dataset split** — from the Dataset screen, create a train/test (or
  train/val/test) split over the tagged runs.
- **Input transform** — create one input transform for the structured task.

### 8. Snapshot, review, and record what was authored

Final `snapshot`, then `git status` / `git diff --stat` for anything unintended, and fill
in the "What was authored" section below with the real ids and counts.

## Tests

No automated tests. Same rationale as phase 1 (architecture.md, "Testing strategy"): no
test loads the fixture, and `verify_seed_loaded` catches rot at the moment it matters.
Verification for this phase is:

- `snapshot` after each group leaves a diff containing only files under
  `.agents/playwright_project/`, reviewed before moving on.
- `reset` from the committed fixture at the end, then land in the app and confirm every
  authored screen renders what was authored: dataset rows with the mixed rating states,
  two run configs on the structured task, the repaired run, the split, the transform, the
  saved prompt.
- No occurrence of the OpenRouter key anywhere in the repo — checked with a grep of the
  working tree before handing off.

## What was authored

Nothing yet. The phase is blocked at step 1 — see below.

## Roadblock: OpenRouter is unreachable from this container

Connecting OpenRouter through the UI (Settings → Providers → OpenRouter → paste key →
Connect) fails with:

```
Failed to connect to OpenRouter. Error: HTTPSConnectionPool(host='openrouter.ai', port=443):
Max retries exceeded with url: /api/v1/chat/completions
(Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden')))
```

This is not the key and not Kiln. All outbound HTTPS from this session goes through the
agent egress proxy, and `openrouter.ai:443` is denied by policy at the gateway — the
proxy's own status endpoint records it as `connect_rejected … gateway answered 403 to
CONNECT`, and a bare `curl https://openrouter.ai/api/v1/models` fails the same way with
no Kiln in the picture. The proxy README is explicit that a 403 is an organization egress
denial that must be reported rather than retried or routed around.

The denial is not OpenRouter-specific: `api.openai.com`, `api.deepseek.com` and
`api.fireworks.ai` (the other provider serving `deepseek-v4-flash`) are all denied the
same way. `generativelanguage.googleapis.com` does answer, and no local model runtime is
installed (`ollama` is absent).

Every remaining step of this phase depends on real generation, so nothing further can be
authored: runs, both run configs, ratings, the repair and the dataset split all require
runs to exist first.

The key never reached disk — Kiln only stores a provider key after the validation call
succeeds, and the sandbox's `settings.yaml` still holds only the three seeded lines. The
key is absent from the working tree; the only place it appeared locally was a
`playwright-cli` page snapshot under the gitignored `.playwright-cli/`, which was deleted.

Unblocking needs one of:

1. `openrouter.ai` allowed through this session's egress policy, after which this plan
   runs as written.
2. A different provider whose host is already allowed, plus a key for it — which changes
   the model every run in the fixture is generated with, so it is the user's call, not
   the implementing agent's.
3. Authoring this phase somewhere with unrestricted egress.
