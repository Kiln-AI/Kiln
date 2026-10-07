---
status: draft
---

# Architecture: Model Sweep

## Shape

One skill, `.agents/skills/kiln-model-sweep/`, drives a run. It is a prompt (SKILL.md) that calls small deterministic scripts for everything that has a right answer, and uses the model only for the judgment steps: reading Slack hints, writing the PR body, writing the needs-discussion comment, and deciding how to answer a PR comment. The host is a one-line prompt that invokes the skill with flags.

```
host (scheduled task | cloud routine)
  └─ claude session: "Read .agents/skills/kiln-model-sweep/SKILL.md and run it with: --mode sweep --host local"
       ├─ scripts/sweep_env.sh        worktree, venv, key availability (booleans), bot identity
       ├─ Slack connector (read)      #models since last run  →  hints.json   [model step]
       ├─ scripts/discover.py         catalogs + backfill  →  candidates.json
       ├─ per candidate: claude-maintain-models P2–P3 (edit ml_model_list.py)   [model step, gates pre-answered]
       ├─ scripts/run_paid_tests.py   smoke + full suite per (enum, provider)  →  results.json + table.md
       ├─ scripts/classify_diff.py    easy | needs-discussion, with reasons
       ├─ scripts/deprecations.py     check_provider + adapter smoke on dead entries  →  deprecations.json
       ├─ scripts/open_prs.py         branches, PR create/update under the active identity, body sections
       ├─ scripts/slack_post.py       drafts only → models webhook; ready PRs get reviewers requested, the team's PR bot posts the card
       ├─ scripts/staleness.py        scan repos  →  table  →  edit the living issue
       ├─ scripts/pr_feedback.py      new comments on model-sweep/* PRs  →  feedback.json ; update-body
       └─ run report (markdown) printed at the end, always
```

Scripts live in `.agents/skills/kiln-model-sweep/scripts/`, Python 3.12, run with `uv run python`, importing `kiln_ai` where needed. Shared provider logic comes from the existing `.agents/scripts/provider_utils.py`. Nothing here is a Kiln runtime dependency; the skill ships with the repo like the other `.agents/skills`.

## GitHub transport

Every GitHub read and write goes through one adapter with two backends: `gh` where it holds a valid token (a laptop, GitHub Actions), and the GitHub MCP tools in the cloud sandbox, where `gh` has none (smoke run 1, 2026-10-01). The commands named in this document are the `gh` spelling; the MCP backend maps one to one (`list_pull_requests`, `create_pull_request`, `update_pull_request`, `pull_request_read`). The skill states the cloud rule outright.

## Modes and Flags

`SKILL.md` accepts, in the invoking prompt:

| Flag | Values | Effect |
|---|---|---|
| `--mode` | `sweep` (default), `comments` | `comments` runs only §Feedback and the report |
| `--host` | `local`, `cloud` | worktree vs plain checkout; where keys and tokens are looked for |
| `--dry-run` | flag | everything runs, but no push, no PR, no comment, no Slack post, no issue edit; the report lists what would have happened |
| `--skip-paid` | flag | discovery, edits and classification run; paid tests are not run and every add is ⚠️ untested |
| `--only` | comma list of model names or links | restrict candidates (used for smoke tests and for "add X" asks) |

## Data Files

All intermediate files live under `.model-sweep/` in the worktree, git-ignored, and are quoted into the run report. Shapes:

- `hints.json`: `[{ts, author, text, kind: model|coverage|gotcha, model_hint, provider_hint, link}]`
- `candidates.json`: `[{friendly_name, family, suggested_enum, providers: [{provider, model_id, source, verified: bool}], hint_refs: [ts], gotchas: [text]}]`
- `results.json`: `[{enum, provider, smoke: pass|fail|skip, full: pass|fail|skip, retry: bool, error: str|null, cost_note}]`
- `classification.json`: `{verdict: easy|needs-discussion, reasons: [str], files_touched: [path]}` per branch
- `deprecations.json`: `[{enum, provider, model_id, listing: present|absent|unknown, adapter_smoke: pass|not_found|error, verdict: dead|alive|expiring|unknown, replacement}]`
- `feedback.json`: `[{pr, comment_id, author, body, in_scope: bool, action}]`

## Components

### sweep_env.sh

- `--host local`: `git -C <main checkout> fetch origin`, `git worktree add -b model-sweep/run-<date> <sibling dir> origin/main`; `uv sync` happens lazily via `uv run`. Removes the worktree on exit unless a branch was pushed from it.
- `--host cloud`: uses the checkout as is.
- Prints key availability as booleans by importing `kiln_ai.utils.config.Config` (local) or reading the environment (cloud). Never prints a value.
- Resolves the GitHub identity: in v1 the operator's own credentials (the cloud session's GitHub App grant, or `gh` on a laptop); when a bot identity exists later, its token from the keychain (local) or an environment variable (cloud). If no identity can write, later steps run as if `--dry-run` for anything that writes to GitHub, and the report says why.
- Reads `SLACK_MODELS_WEBHOOK` and the reviewer list from the environment and reports each as present or absent, booleans only.

### discover.py

Inputs: `hints.json`, `ml_model_list.py` on `main`, open `model-sweep/*` and `add-model/*` PR branches, whatever account authored them (fetched; their `ml_model_list.py` diffs count as "already covered").

- Sources, in the order the maintain-models skill uses them: LiteLLM `model_catalog` (one search per hint family plus the standing list of families; budget 60 requests, leaving headroom under the 100/day limit), `models.dev/api.json`, `openrouter.ai/api/v1/models`, Together (`TOGETHERAI_API_KEY` if present), Featherless, Fireworks model pages, SiliconFlow.
- Lagging-provider backfill: for the 10 most recently added models (by `git log -S` on their enum), check Fireworks, Together, SiliconFlow for a matching slug not yet in the entry.
- Output `candidates.json`. A candidate with zero verified providers is dropped and listed in the report under "unverifiable".
- Fails soft per source: a 4xx/5xx or timeout marks that source skipped in the report and continues.

### Model edit step (prompt, not script)

For each candidate the skill follows `claude-maintain-models` Phases 2 and 3 verbatim, with the consent gates pre-answered as the functional spec §6 lists. Edits go only into `ml_model_list.py`. A new `ModelFamily` is allowed only if it needs no code outside that file; otherwise the candidate goes to a discussion branch untouched, with the reason recorded.

After each edit: `uv run ruff format libs/core/kiln_ai/adapters/ml_model_list.py` and `uv run pytest -q libs/core/kiln_ai/adapters/test_ml_model_list.py`. A failing unit test moves the candidate to discussion.

### run_paid_tests.py

- Input: `(enum, provider)` pairs from the diff (parsed from `ml_model_list.py`, not from the model's memory).
- Bridges keys exactly as maintain-models Phase 4 does: `Config.shared().<attr>` into the env names from `libs/core/kiln_ai/utils/config.py`, both Fireworks variables, `ANTHROPIC_API_KEY` from `KILN_ANTHROPIC_API_KEY`. Prints booleans only.
- Per pair: `uv run pytest --runpaid --ollama -q -p no:cacheprovider -k "test_data_gen_sample_all_models_providers[ENUM-PROVIDER]"`; then `uv run pytest --runpaid --ollama -q -k "ENUM"`; then the extractor test for the enum. On any failure, one retry with `-n 0`. Vertex, Bedrock, Ollama, Docker Model Runner pairs are recorded `skip` with the reason.
- Output `results.json` and a markdown table in the ✅/⚠️/❌ style the maintain-models PR body uses.
- `--skip-paid` writes every pair as `skip: no keys on this host`.

### classify_diff.py

Input: `git diff origin/main...HEAD --name-only` and the unified diff of `ml_model_list.py`, plus `results.json`.

Rules, in order; the first hit wins:

1. Any path other than `libs/core/kiln_ai/adapters/ml_model_list.py` → needs-discussion (`files_touched`).
2. Successor migration → easy for the lines it owns: a provider entry that gains `deprecated=True` in this diff may lose its `suggested_for_*` lines, and a new `KilnModel` may be added beside it. Those removed flag lines are excluded from rules 3 and 4. Any other change in the same diff is still judged by the rules below.
3. Any removed line that is not whitespace, a trailing-comma move, or a line excluded by rule 2 → needs-discussion (`deletion`).
4. Any changed line containing `suggested_for_` or `featured_rank`, other than lines excluded by rule 2 → needs-discussion (`flag_change`).
5. Any `results.json` row with `fail` after retry → needs-discussion for that enum (`test_failure`), and the enum is split out of the adds branch.
6. Otherwise easy.

Unit-tested with fixture diffs for each rule, including a successor-migration diff (old provider entry deprecated with its flags removed, successor model added) that must classify as easy and land in the adds PR.

### deprecations.py

- Calls `check_provider.py all` through a thin import after `extract_models.py --local` (new flag: read `built_in_models` from the checkout instead of the published config; this is a two-line change to the existing script, done in the same PR as the skill).
- For every entry the listing reports absent, runs the adapter smoke test for that `(enum, provider)`. Verdicts: `dead` only on a not-found/inaccessible failure; `alive` if the smoke passes; `expiring` when LiteLLM carries a future `deprecation_date`; `unknown` when the provider was unreachable.
- Writes `deprecated=True,` after the `model_id=` line of each `dead` entry, 16-space indent, and asserts the entry carries no `suggested_for_*` flag (the unit test enforces this too).
- `expiring` and `unknown` are report-only.

### open_prs.py

- Branch names: `model-sweep/adds-<date>`, `model-sweep/deprecations-<date>`, `model-sweep/discuss-<slug>-<date>`. Dedup: before creating, list the repository's open PRs whose head branch matches `model-sweep/*` or `add-model/*`, whatever account authored them (in v1 that is the operator's account); a model already covered is pushed to that branch instead. Dedup never keys on the author.
- Push target: the repository itself when the configured GitHub identity has push rights (the operator's account in v1), else a fork of it (created once).
- PR body: generated by the model following `open-pr`, then the script appends the evidence table and, for discussion PRs, posts the first comment and marks the PR draft. Title `WIP: chore: ...`. Labels applied only if `gh label list` succeeds for the bot.
- Commit message trailer `Co-Authored-By: Claude <noreply@anthropic.com>`; commits with `--no-verify` after `uv run ./checks.sh --agent-mode` passed in the worktree. Greps the diff for `print(` and `TODO|FIXME` and refuses to push on a hit.
- Never `--force`, never merge, never approve.

### slack_post.py

- Drafts only. One incoming-webhook URL from the environment, `SLACK_MODELS_WEBHOOK`, for draft PRs that need a decision; the message carries the inconsistency and the numbered options from the PR's **Decisions required** section, then the cc line for the Slack user id in the run settings. A missing variable skips the post and is named in the run report. No connector fallback; the connector would post as the operator.
- Ready PRs are not posted. `open_prs.py` requests the reviewers from config on creation (and when a draft is marked ready); the team's PR bot posts and maintains the card in the PR channel for any open, non-draft PR with reviewers requested. Decided 2026-10-05.

### staleness.py

- Repos: `Kiln-AI/Kiln`, `Kiln-AI/kiln_server`, from config. Local host uses the sibling checkouts after `git fetch`; cloud host clones shallow.
- Reference detection: `ModelName.<enum>` tokens; every `model_id` string from `built_in_models` searched verbatim; every `friendly_name` searched case-insensitively in `.py`, `.ts`, `.svelte`, `.md`, `.yaml`, `.json`, excluding `ml_model_list.py` itself, tests named `test_*`, `node_modules`, `.venv`.
- Join: status from `built_in_models` (live / deprecated on all providers / absent); newer same-family model = highest `featured_rank` or newest entry in the same `ModelFamily` whose enum sorts later; age from `git log --follow -S<enum> --format=%ad --reverse | head -1` on `ml_model_list.py`.
- Output: one markdown table sorted by repo then file; a second table from `check_finetune.py static` and `fireworks`. `gh issue edit <n> --body-file` on the issue titled "Model staleness" (created on first run with a marker comment `<!-- model-sweep:staleness -->` so the script finds it by marker, not by title).

### pr_feedback.py

- `list`: open PRs whose head branch matches `model-sweep/*`, whatever account authored them; human comments and review comments newer than the routine's last commit on that branch (the PR's creation when there is none); bot status comments excluded. Writes `feedback.json` with an `in_scope` guess from §3 rules (edits to `ml_model_list.py`, re-running tests, body text changes are in scope).
- The skill acts on in-scope items (edit, test, push) and records each in a dated **Updates** section of the PR body; out-of-scope items get a line in the body's **Decisions required** section and no push.
- `update-body --pr N --section updates|decisions --body-file f`: edits the PR body only. There is no reply command; the routine never writes a comment or review under the human account it runs as.

### Run report

Always written, even on failure, as the session's final message: counts, branches and PR links, per-source status, unverifiable candidates, skipped providers with reasons, deprecation verdicts, feedback handled, and anything the operator must do (e.g. "bot token missing: ran as dry-run for GitHub writes").

## Host Prompts

**Local scheduled task** (`~/.claude/scheduled-tasks/model-sweep/SKILL.md`, cron 07:00 and 13:00 America/Toronto, weekdays):

> In /Users/mikechatzidakis/dev/Kiln/Kiln read `.agents/skills/kiln-model-sweep/SKILL.md` and run it with `--mode sweep --host local`. (13:00 task: `--mode comments --host local`.)

**Cloud routine** (the operator's cloud environment, Slack connector attached, Opus 5.5, cron `0 11 * * 1-5` UTC). The message carries only the run settings and an instruction to fetch the skill from the branch under test; see `routine_prompt.md`:

> Run settings: models channel, `SLACK_CC_USER_ID`, the two webhook variables, and the skill source branch. Then: `git fetch origin <branch> && git show origin/<branch>:.agents/skills/kiln-model-sweep/SKILL.md > /tmp/kiln-model-sweep.md`, read it in full, follow it exactly; all work branches from `origin/main`; stop and report if the fetch fails.

The scheduler takes a UTC cron and no timezone, so `0 11 * * 1-5` is 07:00 America/Toronto in summer and 06:00 in winter. The functional spec accepts the drift; move the routine to `0 12 * * 1-5` after the autumn change if the local hour matters.

Network allowlist for the cloud environment is the provider domain list the team keeps for cloud environments plus `api.github.com` and `slack.com`.

## Secrets and Identity

v1 runs under the operator's own GitHub account (functional spec, Decisions). The bot identity below is the later target; nothing in the run logic depends on which identity is active.

- Provider keys: Kiln `Config` on the local host. Never in the cloud environment.
- GitHub identity: v1 uses the operator's own credentials, so nothing extra is stored. A later bot identity would be a token in the keychain (local) or an environment variable (cloud), scoped to public-repo writes.
- Slack: one incoming-webhook URL (models channel) as an environment variable on the host; on a laptop, a keychain item read into the environment by the task. The PR channel is the PR bot's.
- Nothing is ever echoed. `sweep_env.sh` prints `HAS_<NAME>=true|false` only.

## Error Handling

- Per source and per provider: isolate, mark skipped, continue. A run never dies on one provider.
- Per candidate: isolate; a failing edit, test or unit test moves it to discussion rather than aborting the run.
- GitHub or Slack write failure: the report lists the exact command to retry; branches stay pushed.
- Worktree cleanup runs in a trap; a worktree with a pushed branch is kept and named in the report.

## Testing Strategy

- Unit tests (`pytest`, free, in the skill's `tests/`): `classify_diff.py` against fixture diffs for each rule; `discover.py` against recorded catalog responses (`responses` fixtures), including the LiteLLM-quota fallback; `staleness.py` against a fixture repo tree; `deprecations.py` verdict table; `open_prs.py` branch naming and dedup with a stubbed `gh`.
- Smoke 1, local: `--dry-run --only "<one known-new model>"`. Expect candidates, an edited worktree, a real paid run for that model, a classification, and a report listing the PR that would have been opened.
- Smoke 2, local, live: same without `--dry-run`. One PR under the active identity, one Slack post.
- Smoke 3, cloud: `--dry-run --skip-paid --only "<same model>"` as a routine run-now. Records: Slack connector attached, sources reachable, author identity, duration.
- The debug_detector greps run as a unit test over the skill's own scripts.
