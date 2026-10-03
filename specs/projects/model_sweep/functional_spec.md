---
status: draft
---

# Functional Spec: Model Sweep

## Overview

A scheduled, unattended run that turns the existing model-maintenance skills into a routine. Each weekday morning: read hints from #models, discover new models, add the easy ones, verify them with the paid tests, find confirmed deprecations, open PRs as Claude, announce each PR in Slack (drafts in the models channel, ready PRs in the PR review channel), answer PR feedback through the PR body, and refresh a staleness report for the models hard-coded across Kiln-AI repos.

Success state for a quiet day is silence: no PR, no Slack post. The staleness report still refreshes.

**The host is decided by a smoke test, not up front.** The skill `kiln-model-sweep` is host-agnostic and has a dry-run mode. Phase 1 runs it as a desktop-app scheduled task on the operator's Mac, where the provider keys already live. Phase 2 runs the same skill as a Claude Code cloud routine in the operator's cloud environment, paid tests off, and records what works: Slack connector attach, network allowlist, PR author identity, run time. Whichever host passes becomes v1. The cloud-brain-plus-GitHub-Actions design in §9 remains the long-term target because it is the only one where no agent holds a provider key, which is the team's rule for cloud environments (`.config/utils/claude_cloud_setup.md`).

## 1. Trigger and Runtime

- Runs every weekday at 07:00 America/Toronto, plus a 13:00 comments-only run.
- **Local host**: a desktop-app scheduled task on the operator's Mac. The Mac must be awake with the app open. Provider keys come from the operator's Kiln config. The run creates a fresh worktree of `Kiln-AI/Kiln` from `origin/main`, never touches the live checkout, and removes the worktree at the end.
- **Cloud host**: a Claude Code cloud routine in the operator's cloud environment with a fresh checkout. Paid tests run there only if provider keys are present, which the team's cloud policy forbids; the smoke test therefore runs with `--skip-paid`, and every entry it would add is marked ⚠️ untested in the PR until a local or Actions run tests it.
- No cap on new models per run and no spend ceiling. An interrupted run has already pushed its finished branches; the rest carries over.
- Every GitHub action (branch, PR, comment) is made by the machine-user account `kiln-claude` through its own token, never through the operator's login. Every Slack post is made by a Slack app named Claude, never through the operator's user token. Fallbacks are in §4.2. In the cloud, the `kiln-claude` token would have to be an environment variable, which is itself a secret in a cloud environment; the smoke test records what author the routine produces without it.
- The run is stateless. "Since the last run" is derived from the newest `kiln-claude` PR or commit, with a 7-day floor, so no host needs persistent disk.

## 2. Inputs

### 2.1 Slack hints

- Source: the models channel from the run settings (default `#models`), messages since the last successful run, with a floor of 7 days. Read through the Slack connector available to the session (reads are fine under the operator's identity; only posts need the Claude identity).
- Extracted: model names and announcement links, provider-coverage requests ("we don't have X on cerebras"), and gotchas (for example "Opus 5.5 rejects temperature != 1"). Gotchas are carried into the PR body for the matching model.
- Hints are candidates, not instructions. A hinted model is added only if it verifies against a provider catalog like any discovered model. Text in Slack never changes the routine's rules.

### 2.2 Provider discovery

- Reuses the sources already in `claude-maintain-models`: LiteLLM catalog (100 free requests/day), models.dev, OpenRouter, Together, Featherless, Fireworks model pages, SiliconFlow, plus the lagging-provider backfill (Fireworks, Together, SiliconFlow) that the skill runs every time.
- A candidate is "new" if its `model_id` is absent from `ml_model_list.py` on `main` and from every open PR authored by `kiln-claude`.

### 2.3 Deprecation signals

- Reuses `kiln-check-deprecation/scripts/check_provider.py` across all providers that have a key in the operator's config, and the LiteLLM `deprecation_date` field.
- The extractor must read `built_in_models` from the checkout, not the published remote config, so entries merged since the last publish are covered. (Today's script reads the published config; this is a one-flag change.)
- A provider entry is "confirmed dead" only when Kiln's own adapter fails the paid smoke run with a not-found or inaccessible error, the same rule used on 2026-09-26 for the Fireworks cut-off. A listing that merely drops the model is not enough on its own.
- "Expiring soon" entries are reported, never marked.
- Successor slugs (team ruling 2026-10-01): when a provider replaces a slug with a successor checkpoint, the old provider entry is deprecated (its suggested flags removed) and the successor is added as a distinct model with its own enum and suffixed name. The `model_id` is never edited in place, so pinned evals keep their history.

### 2.4 Open model-sweep PRs

- Open PRs on `model-sweep/*` branches, whatever account authored them, are read for new human comments since the routine's last commit on that branch (see §5).

## 3. Classification: Easy vs Needs Discussion

A change is **easy** when all of these hold:

1. The diff touches only `libs/core/kiln_ai/adapters/ml_model_list.py`.
2. The change is an added `ModelName`, an added `KilnModel`, an added `KilnModelProvider`, or `deprecated=True` on an existing provider entry. Nothing is deleted.
3. The added entries pass the paid smoke test and the model's full `-k` suite on every provider that can run unattended (see §6).
4. No `suggested_for_*` or `featured_rank` value changes.

Everything else **needs discussion**, including: any file other than `ml_model_list.py`, a new parameter or adapter change needed to make a test pass, a new provider, a new `ModelFamily` that needs code elsewhere, a test failure that persists after one serial retry, a recommendation-flag change, and any "expiring soon" deprecation.

One explicit exception: a successor migration, where a provider stops serving a slug and serves a successor checkpoint. The old provider entry gets `deprecated=True` and loses its `suggested_for_*` flags, and the successor is added as a distinct model. Both edits count as one easy change and go in the adds PR for that run, not the deprecations PR, and the flag removal is not a flag change for the purpose of this rule (see §2.3 and the skill's successor-slug gate).

The classification is computed from the diff paths and the test results, not from the model's opinion.

## 4. Outputs

### 4.1 Pull requests

All PRs: semantic-commit title, `chore: ...`; the `WIP:` prefix means draft and is used only on needs-discussion PRs (ruling 2026-10-01; this overrides open-pr's always-WIP rule). A draft that becomes ready loses the prefix. Body: the template's human header pre-populated (ruling 2026-10-01: Description written by the routine, Architecture Review "Small change", Review Style "Mixed", Agentic Code Review "addressed all AI feedback", Key decisions `ML Model Update`, Paths `ml_model_list.py`, UI "No UI"; Author Review left unchecked for the author; no CLA line), then open-pr's Agentic PR Summary with the per-test evidence table from `claude-maintain-models`. No `print(` and no TODO/FIXME in the diff. Branches: `model-sweep/adds-YYYY-MM-DD`, `model-sweep/deprecations-YYYY-MM-DD`, `model-sweep/discuss-<model>-YYYY-MM-DD`.

- **Adds PR**: one per run, every easy add from that run. Body ends with a "Candidates for suggested flags" list for a human; the routine never sets those flags.
- **Deprecations PR**: one per run, every confirmed-dead entry, except entries deprecated as part of a successor migration, which travel with their successor in the adds PR (§3). Recommendation flags and deprecations stay in separate PRs (team ruling of 2026-09-16).
- **Needs-discussion PR**: one per item, opened as a draft. Its body ends with a bold **Decisions required** section between horizontal rules: what the model needs, why it is not an easy add, and the options. No further code lands on it until a human answers.
- **Dedup**: if an open `kiln-claude` PR already covers a model, the run pushes to that branch instead of opening another.
- **Where branches live**: on `Kiln-AI/Kiln` directly if `kiln-claude` has been invited to the org; otherwise on a fork, `kiln-claude/Kiln`, with "allow edits from maintainers" on. Labels (`model-sweep`, `needs-discussion`) are applied only when the account has triage rights; the title prefix and branch name carry the same information either way.
- The routine never merges, approves, or force-pushes.

### 4.2 Slack post

Authoritative rule, matching the skill and the smoke log: one message per PR the run opened, through the operator's Slack app incoming webhooks. A draft PR (needs a decision) is announced in the models channel through `SLACK_MODELS_WEBHOOK`; a ready PR is announced in the PR review channel through `SLACK_PRS_WEBHOOK`. A draft that a later run marks ready is announced again in the PR review channel. Each message carries the why (the inconsistency and the options for a draft, the TLDR for a ready PR) and a cc line for the Slack user id in the run settings. A missing webhook variable skips that post and is named in the report. No further discussion in Slack; replies there are treated as hints on the next run, nothing more.

### 4.3 Paid tests

- Run locally, inside the worktree, exactly as `claude-maintain-models` specifies: smoke test then the model's full `-k` suite with `--runpaid --ollama`, keys bridged from Kiln `Config` into the environment (both Fireworks variables), availability printed as booleans only. One serial retry (`-n 0`) on a flake.
- A ❌ moves that model out of the adds PR and into a needs-discussion PR in the same run.

### 4.4 Staleness report

- Scope: hard-coded model references across `Kiln-AI/Kiln` and `Kiln-AI/kiln_server` (both are checked out on the operator's Mac; the run fetches `origin/main` of each); more repos by config. A reference is a `ModelName` enum, a provider `model_id` string, or a friendly name used in a prompt, default, or config.
- Per reference: repo and `file:line`, provider, status in `ml_model_list.py` (live, deprecated, absent), the newest same-family model in Kiln if one is newer, and the age of the entry in Kiln from `git log` on its `ml_model_list.py` line.
- Output: one living GitHub issue in `Kiln-AI/Kiln` titled "Model staleness", edited in place each run by `kiln-claude`. The fine-tune audit (`kiln-check-finetune-deprecation`, report-only) appends to the same issue.
- Staleness never produces a PR. Changing a default model is a human decision.

### 4.5 Remote config publish check

- Added 2026-10-01 at the operator's request. Kiln clients read the model list from the published remote config, built by `publish_remote_config.yml` on a push to the `remote_config` branch. The team's flow is a PR with head `main` and base `remote_config`, merged by a human.
- Every run diffs `origin/remote_config..origin/main` on the files the config is built from: `ml_model_list.py`, `ml_embedding_model_list.py`, `reranker_list.py`, `remote_config.py`. No diff: nothing to do. A diff is a candidate only: the run generates the config JSON from both refs and compares them, so a comment-only change to those files (as on 2026-10-02) publishes nothing.
- A diff with an open PR into `remote_config` already present: no new PR. The routine refreshes its own PR's body with an **Updates** section; a human's PR is left alone and reported with its age.
- A diff with no such PR: run the backwards-compatibility test the publish workflow runs, check `merge-tree` for conflicts, and open head `main` into base `remote_config`. Clean and passing: ready PR announced in #prs. Conflicts or failure: draft PR with **Decisions required**, announced in #models.
- The routine never merges it. The merge is the publish decision and stays human.

## 5. PR Feedback Loop

- A human comments on a model-sweep PR. The next run reads it, pushes the fix to the PR branch when the request is within scope (model-list edits, test re-runs, body corrections), and records what changed in a dated **Updates** section of the PR body. It never replies in the thread.
- Requests outside §3's easy set (code outside `ml_model_list.py`, flag changes, new providers) get a line in the **Decisions required** section that states the boundary and asks a human to decide; nothing is pushed for them.
- Latency is next run. v1 schedules a second, comments-only run at 13:00 America/Toronto on weekdays so a morning comment is answered the same afternoon.

## 6. Unattended Rules (pre-answered consent gates)

The existing skills stop and ask at several points. The routine answers them as follows:

| Skill gate | Routine answer |
|---|---|
| Which discovered models to add | All verified candidates, newest first |
| Slug cannot be verified | Skip, list in the run report |
| Lagging-provider backfill: bundle or separate | Bundle into the adds PR |
| SOTA "suggested" flag or zero-sum swap | Never; list as candidates in the PR body |
| Consent to run paid tests | Granted |
| Vertex needs `gcloud` login | Skip Vertex; entries added with a ⚠️ untested mark |
| Bedrock needs `aws` CLI, Ollama and Docker Model Runner need local daemons | Same as Vertex |
| Any ❌ test | Move that model to a needs-discussion PR |
| Any ⚠️ flake | Retry once serially (`-n 0`); then needs-discussion |
| A provider key missing in the operator's config | Skip that provider with a ⚠️ |
| Deprecation: confirm before marking | Auto for confirmed dead only |
| Expiring soon | Report only |
| Fine-tune list changes | Report only |
| open-pr: ambiguous base branch | Always `main` |
| open-pr: watch window | Replaced by §5 |

## 7. Configuration

Lives with the skill in `.agents/skills/kiln-model-sweep/`: Slack channel id, providers to skip unattended, repos to scan for staleness, branch prefix, the GitHub account name. The scheduled task's prompt on the operator's Mac is one line: run the skill. Provider keys stay in the operator's Kiln config. The `kiln-claude` token and the Slack app token live in the operator's macOS keychain and are read into the session's environment by the task, never written to the repo or the transcript.

## 8. Security

- **Rule of 2026-10-01: the routine never writes a PR comment, review comment or review.** PRs are authored under the operator's account and a comment would read as his words. The PR body and commit messages are its only voice.
- Slack messages and PR comments are untrusted input. They can propose a model; they cannot change the rules in §3 or §6.
- `kiln-claude` holds the minimum: public-repo scope plus write on its fork, or on `Kiln-AI/Kiln` if invited. It never holds provider keys.
- Secret values are never printed; availability is logged as a boolean.
- The run never touches the live `Kiln` or `kiln_server` checkouts; it works in a worktree it creates and removes.
- The routine never merges and never force-pushes.

## Out of Scope

- Setting `suggested_for_*` or `featured_rank` flags.
- Adding a new provider (discussion PR only).
- Changing default models in kiln_server or elsewhere (staleness report only).
- Any discussion in Slack.
- Discord announcements. Dropped on 2026-10-01; no longer needed.
- Merging PRs.

## Edge Cases

- A provider API is down: skip that provider for the run, say so in the run report, do not deprecate anything on that provider.
- LiteLLM daily limit reached: fall back to models.dev and OpenRouter for the rest of the run.
- A model is already in an open `model-sweep` PR: push to that branch, do not open another.
- `main` moved under an open adds PR: rebase the branch, re-run the model-list unit tests, push.
- Nothing new and nothing dead: no branch, no PR, no Slack post. The staleness issue still refreshes.
- A human pushes to a model-sweep branch directly: the next run leaves that PR alone and notes it in the run report.
- The brain's run ends on the host's time limit: finished branches are pushed, the rest carries over, the run report says so.
- The manifest is missing or malformed on a `model-sweep/**` push: the hands open nothing and post a failing check with the parse error.

## 9. v2: Cloud Brain and GitHub Actions Hands

The later target, once the team-level pieces exist. The skill is unchanged; only the host moves.

- **Brain**: a Claude Code cloud routine on an environment built from `.config/utils/claude_code_vm_setup.sh`, with no secrets. It reads, decides, edits, runs the free checks, and pushes `model-sweep/*` branches with a run manifest (`.model-sweep/run.json`: title, body, tests to run, classification, replies owed).
- **Hands**: GitHub Actions in `Kiln-AI/Kiln`, deterministic, no LLM. An org GitHub App named Claude opens the PRs and posts comments. A pytest job with provider keys in Actions secrets runs the paid tests and posts the evidence table; the same job runs on any PR a maintainer labels `paid-model-tests`, closing the gap a teammate hit on 2026-08-28. The classification is recomputed from diff paths and results, and the hands' verdict wins.
- **Slack**: the team Slack bot posts on `model-sweep` PR open.
- **Feedback loop in minutes**: a comment-triggered Claude Code GitHub Action, posting as the same app, with an Anthropic API key in Actions secrets.
- Asks for the repo admins at that point: the org GitHub App, provider keys as Actions secrets, the bot's post, and an Anthropic key. None of them block v1.

## Decisions Taken (2026-10-01)

- v1 host: Claude Code cloud routine in the operator's cloud environment, chosen on the 2026-10-01 smoke test (see `smoke_log.md`). Paid tests run there with the environment's keys, the operator's call. The local scheduled task is the fallback host. v2 remains the cloud brain plus GitHub Actions hands.
- GitHub identity: PRs are authored as the operator for now (the cloud session acts through the Claude GitHub App as the account owner). "As Claude" waits for a bot identity: a machine-user account or an org GitHub App.
- Slack identity: the operator's Slack app, two incoming webhooks; drafts to the models channel, ready PRs to the PR review channel (§4.2). A team bot may take this over later.
- No cap on models or spend per run.
- Staleness covers Kiln and kiln_server, reported in one living GitHub issue.
- Discord announcement dropped.
- 07:00 America/Toronto on weekdays, plus a 13:00 comments-only run; quiet days stay silent.
