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
       ├─ scripts/open_prs.py         branches, PR create/update as kiln-claude, first comment
       ├─ scripts/slack_post.py       one line per PR (Slack app) or connector fallback
       ├─ scripts/staleness.py        scan repos  →  table  →  edit the living issue
       ├─ scripts/pr_feedback.py      new comments on kiln-claude PRs  →  feedback.json ; reply
       └─ run report (markdown) printed at the end, always
```

Scripts live in `.agents/skills/kiln-model-sweep/scripts/`, Python 3.12, run with `uv run python`, importing `kiln_ai` where needed. Shared provider logic comes from the existing `.agents/scripts/provider_utils.py`. Nothing here is a Kiln runtime dependency; the skill ships with the repo like the other `.agents/skills`.

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
- Exports `GH_TOKEN` for `kiln-claude` from `security find-generic-password -s kiln-claude-gh -w` (local) or `KILN_CLAUDE_GH_TOKEN` (cloud). If absent, sets `SWEEP_BOT=none`; later steps then run as if `--dry-run` for anything that writes to GitHub, and the report says why.
- Exports the Slack app token the same way (`kiln-claude-slack`); if absent, `slack_post.py` falls back to the connector with the `[model sweep]` prefix.

### discover.py

Inputs: `hints.json`, `ml_model_list.py` on `main`, open `kiln-claude` PR branches (fetched; their `ml_model_list.py` diffs count as "already covered").

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
2. Any removed line that is not whitespace or a trailing-comma move → needs-discussion (`deletion`).
3. Any changed line containing `suggested_for_` or `featured_rank` → needs-discussion (`flag_change`).
4. Any `results.json` row with `fail` after retry → needs-discussion for that enum (`test_failure`), and the enum is split out of the adds branch.
5. Otherwise easy.

Unit-tested with fixture diffs for each rule.

### deprecations.py

- Calls `check_provider.py all` through a thin import after `extract_models.py --local` (new flag: read `built_in_models` from the checkout instead of the published config; this is a two-line change to the existing script, done in the same PR as the skill).
- For every entry the listing reports absent, runs the adapter smoke test for that `(enum, provider)`. Verdicts: `dead` only on a not-found/inaccessible failure; `alive` if the smoke passes; `expiring` when LiteLLM carries a future `deprecation_date`; `unknown` when the provider was unreachable.
- Writes `deprecated=True,` after the `model_id=` line of each `dead` entry, 16-space indent, and asserts the entry carries no `suggested_for_*` flag (the unit test enforces this too).
- `expiring` and `unknown` are report-only.

### open_prs.py

- Branch names: `model-sweep/adds-<date>`, `model-sweep/deprecations-<date>`, `model-sweep/discuss-<slug>-<date>`. Dedup: before creating, `gh pr list --author kiln-claude --state open --json headRefName,title`; a model already covered is pushed to that branch instead.
- Push target: `Kiln-AI/Kiln` if `gh api repos/Kiln-AI/Kiln --jq .permissions.push` is true for the bot, else the fork `kiln-claude/Kiln` (created once with `gh repo fork --clone=false`).
- PR body: generated by the model following `open-pr`, then the script appends the evidence table and, for discussion PRs, posts the first comment and marks the PR draft. Title `WIP: chore: ...`. Labels applied only if `gh label list` succeeds for the bot.
- Commit message trailer `Co-Authored-By: Claude <noreply@anthropic.com>`; commits with `--no-verify` after `uv run ./checks.sh --agent-mode` passed in the worktree. Greps the diff for `print(` and `TODO|FIXME` and refuses to push on a hit.
- Never `--force`, never merge, never approve.

### slack_post.py

- With a Slack app token: `chat.postMessage` to `C0AG8U78MNG`, one line per PR: `<title> <url> — N added / N deprecated / needs discussion`.
- Without: prints the same line for the skill to send through the connector with the `[model sweep]` prefix.

### staleness.py

- Repos: `Kiln-AI/Kiln`, `Kiln-AI/kiln_server`, from config. Local host uses the sibling checkouts after `git fetch`; cloud host clones shallow.
- Reference detection: `ModelName.<enum>` tokens; every `model_id` string from `built_in_models` searched verbatim; every `friendly_name` searched case-insensitively in `.py`, `.ts`, `.svelte`, `.md`, `.yaml`, `.json`, excluding `ml_model_list.py` itself, tests named `test_*`, `node_modules`, `.venv`.
- Join: status from `built_in_models` (live / deprecated on all providers / absent); newer same-family model = highest `featured_rank` or newest entry in the same `ModelFamily` whose enum sorts later; age from `git log --follow -S<enum> --format=%ad --reverse | head -1` on `ml_model_list.py`.
- Output: one markdown table sorted by repo then file; a second table from `check_finetune.py static` and `fireworks`. `gh issue edit <n> --body-file` on the issue titled "Model staleness" (created on first run with a marker comment `<!-- model-sweep:staleness -->` so the script finds it by marker, not by title).

### pr_feedback.py

- `list`: open PRs authored by `kiln-claude`; comments and review comments newer than the bot's last comment on that PR; excludes the bot's own. Writes `feedback.json` with an `in_scope` guess from §3 rules (edits to `ml_model_list.py`, re-running tests, body text changes are in scope).
- The skill acts on in-scope items (edit, test, push) and drafts a reply for each item; out-of-scope items get a boundary reply and no push.
- `reply --pr N --comment-id C --body-file f`: posts as `kiln-claude` in the thread (`gh api` on the review-comment or issue-comment endpoint).

### Run report

Always written, even on failure, as the session's final message: counts, branches and PR links, per-source status, unverifiable candidates, skipped providers with reasons, deprecation verdicts, feedback handled, and anything the operator must do (e.g. "bot token missing: ran as dry-run for GitHub writes").

## Host Prompts

**Local scheduled task** (`~/.claude/scheduled-tasks/model-sweep/SKILL.md`, cron 07:00 and 13:00 America/Toronto, weekdays):

> In /Users/mikechatzidakis/dev/Kiln/Kiln read `.agents/skills/kiln-model-sweep/SKILL.md` and run it with `--mode sweep --host local`. (13:00 task: `--mode comments --host local`.)

**Cloud routine** (environment "Models", Slack connector attached, Sonnet 5, cron `0 11 * * 1-5` UTC):

> Read `.agents/skills/kiln-model-sweep/SKILL.md` and run it with `--mode sweep --host cloud --skip-paid`.

Network allowlist for the cloud environment is the provider domain list the team keeps for cloud environments plus `api.github.com` and `slack.com`.

## Secrets and Identity

- Provider keys: Kiln `Config` on the local host. Never in the cloud environment.
- `kiln-claude` GitHub token: macOS keychain item `kiln-claude-gh` locally. Scopes: `public_repo` (and `repo` only if invited to the org for private pushes, which this repo does not need). In the cloud, it would have to be `KILN_CLAUDE_GH_TOKEN`; the smoke test runs without it and records the resulting author.
- Slack app token: keychain item `kiln-claude-slack`, scopes `chat:write`, `channels:history`.
- Nothing is ever echoed. `sweep_env.sh` prints `HAS_<NAME>=true|false` only.

## Error Handling

- Per source and per provider: isolate, mark skipped, continue. A run never dies on one provider.
- Per candidate: isolate; a failing edit, test or unit test moves it to discussion rather than aborting the run.
- GitHub or Slack write failure: the report lists the exact command to retry; branches stay pushed.
- Worktree cleanup runs in a trap; a worktree with a pushed branch is kept and named in the report.

## Testing Strategy

- Unit tests (`pytest`, free, in the skill's `tests/`): `classify_diff.py` against fixture diffs for each rule; `discover.py` against recorded catalog responses (`responses` fixtures), including the LiteLLM-quota fallback; `staleness.py` against a fixture repo tree; `deprecations.py` verdict table; `open_prs.py` branch naming and dedup with a stubbed `gh`.
- Smoke 1, local: `--dry-run --only "<one known-new model>"`. Expect candidates, an edited worktree, a real paid run for that model, a classification, and a report listing the PR that would have been opened.
- Smoke 2, local, live: same without `--dry-run`. One PR from `kiln-claude`, one Slack line.
- Smoke 3, cloud: `--dry-run --skip-paid --only "<same model>"` as a routine run-now. Records: connector attached, sources reachable, author identity, duration.
- The debug_detector greps run as a unit test over the skill's own scripts.
