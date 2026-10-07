# Smoke log

## Run 1: cloud routine, Models environment (2026-10-01)

- Routine: `<routine-id>`, name "Kiln model sweep", created 2026-10-01 15:44 UTC, disabled, cron `0 11 * * 1-5`.
- Environment: Models (`<environment-id>`). Model: Opus 5.5. Tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch, WebSearch.
- Prompt: `routine_prompt.md` as of this date.
- Finding at creation: the API attached the account's claude.ai connectors automatically (Slack, Linear, Claude Docs, Claude Code Remote). The hints step therefore has a Slack tool. Linear and Claude Docs are unneeded; trim to Slack after this run.
- Started by hand with `run` at 2026-10-01 15:45 UTC; session `<session-id>`. Questions this run answers:
  1. Does the routine finish unattended, with the skills' gates pre-answered?
  2. Who is the GitHub author of its commits and PRs?
  3. Do the paid tests run with the environment's keys?
  4. Are the discovery sources reachable under the environment's network policy?
  5. Duration and spend.
- Interim, 15:54 UTC (9 min in):
  - Slack connector attached to the routine works: read #models for 7 days.
  - GitHub MCP tools (`mcp__github__*`) are available in the cloud session.
  - Keys present as env vars: OpenAI, Anthropic (as KILN_ANTHROPIC_API_KEY, bridged), Gemini, OpenRouter, Fireworks + account id, TogetherAI, SiliconFlow, Cerebras, Groq, Featherless, Vertex project id. Unset: HUGGINGFACE_API_KEY, TOGETHER_API_KEY (the Together-named variant).
  - Discovery via models.dev, OpenRouter, provider /models endpoints and web search: 10 new models + 3 lagging-provider backfills; GPT-6.1 Sol skipped because `add-model/gpt-6-1-sol` is already open; Gemini 4 Argon not yet in the API.
  - Edited `ml_model_list.py` (+228 lines), unit tests pass.
  - Paid smoke: Muse Glimmer on Fireworks is catalog-listed but a live call returns NOT_FOUND "not deployed"; the run split it to a needs-discussion item as the rule requires. Full paid suite for the 8 others running.
  - Environment wart: the sandbox `uv` cannot parse `exclude-newer = "7 days"` in pyproject (warning on every uv command). "No setup script configured" on this environment; the team's VM setup wrapper would fix both.
- Interim, 16:02 UTC (17 min in):
  - **Q2 answered: GitHub identity is the operator.** `mcp__github__get_me` in the cloud session returns the operator's GitHub login. Cloud-routine PRs and comments will be authored as the operator, not as Claude, until a bot identity exists.
  - **Q3 answered: paid tests run.** Full suite for the 8 new models: 141 passed, 1 flake (MiMo V2.6 Flash, structured-output CoT) that passed on the `-n 0` retry, 65 skipped, 8 collection errors from the environment (no `tkinter`, desktop tests). Audio and video extraction tests passed for Qwen 3.8 Omni Flash.
  - Deprecation audit: 12 candidates from `check_provider`; 11 fail with not-found in Kiln's adapter test, `glm_5` on SiliconFlow returns 403 "Model disabled", `deepseek_4_pro` on Together is "non-serverless, create a dedicated endpoint". 10 entries marked `deprecated=True` on a separate worktree branch `model-sweep/deprecations-2026-10-01`.
  - Muse Glimmer on Fireworks: NOT_FOUND on a live call despite the catalog listing; split to `model-sweep/discuss-muse-glimmer-30b-2026-10-01`.
  - **Q4, network policy gaps** in the operator's cloud environment: `remote-config.getkiln.ai` and `api.together.ai` are rejected by the sandbox proxy (`connect_rejected`). The run worked around the first by reading `built_in_models` from the checkout, which is what the spec wants anyway. Together catalog reads fail; Together paid tests still worked via `api.together.xyz`.
  - Environment gaps the run repaired itself: `uv` 0.8.17 vs the repo's `required-version >= 0.10` (it rewrote `uv.lock`, then installed uv 0.12.21 and restored the lock); no `node_modules` (ran `npm ci`); no `tkinter` (desktop tests cannot run here).
  - Cost so far: not reported by the run; estimate from the suite size later.
- Interim, 16:12 UTC (27 min in): paid suite finished, deprecations and discussion branches prepared in separate worktrees, `npm ci` plus `checks.sh` ran past 10 minutes and moved to the background, PR bodies being drafted with per-test evidence (for example Grok 4.7: 17 passed, 10 skipped; Qwen 3.8 Omni Flash: 22 passed, 5 skipped).

### Fixes for the operator's cloud environment (from this run)

1. Setup script: paste `.config/utils/claude_code_vm_setup.sh` into the environment's setup-script field. Removes the per-run `uv sync`, `npm ci`, and the `uv` version mismatch (sandbox has 0.8.17, repo requires >= 0.10, which also makes `uv` rewrite `uv.lock` until the run restores it).
2. Network allowlist: add `remote-config.getkiln.ai` and `api.together.ai` (the deprecation scripts use both; `api.together.xyz` already passes). The run reported `connect_rejected` on both.
3. `tkinter` is absent, so `app/desktop/test_desktop.py` cannot be collected; `checks.sh` will always show those collection errors here. Either accept them in the routine prompt or add the package in the setup script.
- Interim, 16:31 UTC (46 min in): `uv run ./checks.sh --agent-mode` ran past 25 minutes in the 4-vCPU sandbox and was killed (exit 143). The run is bisecting the individual checks (ruff, format, ty, schema, web checks). Prompt fix for the next version: in the routine, replace the full `checks.sh` with the targeted checks (`ruff check`, `ruff format --check`, `ty check`, the OpenAPI schema check, the web format/lint/check trio, and `pytest libs/core/kiln_ai/adapters/test_ml_model_list.py`); CI runs the full suite on the PR. The `open-pr` skill's S1 asks for `checks.sh`, so the routine prompt must say explicitly that the targeted set replaces it.
- Interim, 16:38 UTC (53 min in): three branches pushed to `Kiln-AI/Kiln`: `model-sweep/adds-2026-10-01` (8 models, 228 lines), `model-sweep/deprecations-2026-10-01` (10 entries; it noticed Claude Opus 4 is left with no live provider and flags it in the body), `model-sweep/discuss-muse-glimmer-30b-2026-10-01`. Targeted checks all pass; only `tkinter`-dependent desktop tests and the OpenAPI schema script fail to import in the container. PR bodies written (adds body 258 lines with per-test evidence).
- Environment wart: `gh auth status` reports the sandbox `GH_TOKEN` is invalid, so every `gh` command in the skills and in the routine prompt fails there. `git push` and the `mcp__github__*` tools work. Prompt fix: tell the routine to use the GitHub MCP tools for listing, creating, commenting and editing PRs, and never `gh`.
- **Result, 16:41 UTC: success.** 55 minutes, 95 turns. Three PRs on `Kiln-AI/Kiln`, all authored by the operator's GitHub account:
  - [#1849](https://github.com/Kiln-AI/Kiln/pull/1849) `WIP: chore:` adds 8 models, all OpenRouter: MiMo-V2.6 Pro, Pro UltraSpeed and Flash; Grok 4.7; Qwen 3.8 Max Prime and Omni Flash; GLM 5.3 Prime and FlashX. Paid suite 141 passed, 1 flake passed on retry. Body lists Qwen 3.8 Max Prime, GLM 5.3 Prime and GLM 5.3 FlashX as candidates for suggested flags.
  - [#1850](https://github.com/Kiln-AI/Kiln/pull/1850) deprecates 10 provider entries confirmed dead by Kiln's adapter: Claude Opus 4.1 (Anthropic), Gemini 2.0 Flash and Flash Lite (Gemini API), GLM 5 (SiliconFlow, "Model disabled"), and six OpenRouter entries (Claude Opus 4, DeepSeek R1 Distill Llama 70B, Llama 3.2 11B, GPT-5.3 Chat, Gemma 3n 4B, Nemotron 3 Nano free). Flags that Claude Opus 4 is left with no live provider. Report-only: OpenRouter expiry dates on 11 slugs between 2026-10-08 and 2026-11-11; DeepSeek V4 Pro on Together looks dead but Together's catalog host was unreachable.
  - [#1851](https://github.com/Kiln-AI/Kiln/pull/1851) draft, needs discussion: Muse Glimmer 30B on Fireworks returns 404 "not deployed" despite a READY catalog entry. First comment states the options.
  - CI: every finished check green on all three (Python 3.10 to 3.13, lint, schema, web UI, Socket). CodeRabbit skipped because of the `WIP:` prefix.
  - After the final report the session woke three more times on GitHub notifications for its own PRs and triaged them (CI, coverage). A review comment or CI failure would wake it the same way, so PRs opened by a run get a feedback loop without any extra wiring, for as long as that session exists.
  - The run also sent one mobile push with the PR links.

### Answers to the five questions

1. Finishes unattended: yes. Every skill gate was pre-answered correctly; the needs-discussion rule and the deprecation rule both fired on real cases.
2. GitHub author: the operator, through the Claude GitHub App. "As Claude" needs a bot identity; still open.
3. Paid tests: run, with the environment's keys.
4. Network: `remote-config.getkiln.ai` and `api.together.ai` blocked; everything else reachable.
5. Duration 55 min, of which about 15 min was the model work and about 40 min environment overhead (`uv`/`npm` setup, `checks.sh` hang). Spend not reported by the run.

### Prompt changes applied after run 1 (routine updated 2026-10-01)

- Use the GitHub MCP tools for every PR read and write; `gh` has an invalid token in the sandbox.
- Replace `checks.sh` with the targeted checks; name the `tkinter` import failures as environmental in the PR body.
- Read `built_in_models` from the checkout for the deprecation audit; use `api.together.xyz`.
- Upgrade `uv` if the sandbox copy is below the repo's required version; never commit `uv.lock`.
- Connectors trimmed to Slack. Routine enabled, cron `0 11 * * 1-5`.


## Run 2: cloud routine after environment fixes (2026-10-01)

- Started by hand at 16:52 UTC; session `<session-id>`. Same routine, revised prompt, Slack-only connector.
- Environment changes made by the operator before this run: the team's VM setup script pasted into the operator's cloud environment; `UV_SYSTEM_CERTS=true`; network allowlist extended with `raw.githubusercontent.com`, `cdn.playwright.dev`, `playwright.download.prss.microsoft.com`, `remote-config.getkiln.ai`, `api.together.ai`.
- Questions this run answers:
  1. Does the setup script run at provisioning (log should no longer say "No setup script configured"), and does the sandbox come up with a usable `uv`, venv and `node_modules`?
  2. Does dedup against the open `model-sweep/*` PRs leave nothing to add?
  3. Does a quiet day end with no PR and a short report?
  4. Duration without environment overhead.
- **Result, 16:55 UTC: success, quiet day.** Setup script ran at provisioning (56 s). `uv` 0.12.21 already present. Agent time 91 s, 18 turns. Read #models, listed open PRs, fetched the three `model-sweep/*` branches and compared, found the hinted models on `main` or in open PRs, opened nothing, reported why. It did not re-run the deprecation audit or paid tests because nothing changed. It deferred to the earlier sweep on a handful of OpenRouter entries (GPT-6 Sol Pro, GPT-6 Luna Pro, GPT-6.1 Sol Pro, Command A Plus, Solar Mini 4, Aion 3.5, Perceptron Mk1.5, Ternary Bonsai 2 27B, Unbiased Pareto) that run 1 did not add; a normal morning run has no earlier sweep to defer to, so those will be judged fresh.
- Not exercised by this run: the two newly allowed hosts (the prompt still routes around them, which is the preferred behaviour anyway), paid tests, PR creation.

## Run 3: end-to-end repro driven by the operator (2026-10-01, ~17:45 UTC)

- The operator closed #1849, #1850, #1851 and re-ran the routine with the webhooks set on the operator's cloud environment.
- Result: #1854 adds 8 models and 8 provider backfills (ready), #1853 marks 10 dead entries deprecated (ready), #1852 is a draft: Together no longer serves `deepseek-ai/DeepSeek-V4-Pro` but the entry carries suggested flags, so the sweep proposed the `-0813` slug and asked. All three bodies carry a TLDR; #1852 carries **Decisions required**; none of the three has a comment under the operator's account.
- Slack: the draft post for #1852 landed in #models at 13:53 EDT with the why and the options. Ready posts for #1853 and #1854 landed in #prs at 13:53 EDT, each with a one-sentence Summary from the PR's TLDR. Both Slack paths confirmed end to end.
- Same day, a teammate asked in #models to merge `main -> remote_config`; that became the remote-config publish check in the prompt.

## Remote config publish check: added 2026-10-01

- Flow confirmed from history: PRs #1557, #1605, #1631, #1756 were all head `main` into base `remote_config`, merged by a human; `publish_remote_config.yml` builds `kiln_config_v2.json` from `ml_model_list.py`, `ml_embedding_model_list.py` and `reranker_list.py` on the push and deploys it.
- State at 2026-10-01 18:00 UTC: the operator's #1810 (opened 2026-09-23, head `main`) is MERGEABLE and CLEAN with 28 checks green; merging it publishes Sonnet 5.5, Sonnet 5, GPT-6.1 Sol and three Fireworks deprecations. The routine's step treats it as a human-opened pending PR: reports it, opens nothing. After it merges, future publish PRs are routine-opened and get a daily **Updates** refresh while they wait.
- Publish paths in practice (GitHub activity API): the operator merges PRs head `main` into `remote_config` (2026-07-09, 07-22, 08-17, 09-08); a maintainer force-pushes `main` onto `remote_config` (2026-08-17, 08-19, 09-28). Each push ran "Publish Remote Config" successfully (last: 2026-09-28 19:03 UTC on 3d3ff7255). The live `kiln_config_v2.json` has 264 models and matches `remote_config` (includes Opus 5.5, GPT-6 Sol, Gemini 3.8 Flash; lacks Sonnet 5.5 and GPT-6.1 Sol, which landed on main after the force push). Note: `gh run list --event push` under-reported these runs; the raw `actions/runs?branch=remote_config` API is the reliable check. The routine's diff-of-tips check is correct under both paths.
- Side effect to know: while a PR with head `main` into `remote_config` is open (#1810 today), every push to `main` also triggers the publish workflow's pull_request job (compatibility test only, no deploy).
- Prompt updated to v4 with the step; `routine_prompt.md` matches the live routine.

## Slack announcement: decided 2026-10-01

- Workflow Builder's webhook trigger was not available in the workspace, so the carrier is a Slack app the operator created, with two incoming webhooks: one into `#models`, one into `#prs`.
- Routing: a draft PR (needs a decision) is announced in `#models`; a straightforward PR in `#prs`; when a draft is marked ready for review it is announced in `#prs` and loses the `needs-discussion` label.
- Carrier: the GitHub Action `.github/workflows/model_sweep_announce.yml` (drafted in this worktree) on `pull_request: opened, ready_for_review` for `model-sweep/*` branches. Needs two repo secrets, `SLACK_MODELS_WEBHOOK` and `SLACK_PRS_WEBHOOK`; the operator has push and triage but not admin on the repo, so an admin adds them.
- Decision 2026-10-01: the routine posts itself. the operator sets `SLACK_MODELS_WEBHOOK` and `SLACK_PRS_WEBHOOK` as environment variables on the operator's cloud environment; the prompt carries the posting step with the same routing. The Action stays the v2 carrier (same secret names), and it is the only thing that can announce a ready-for-review transition on the event itself.
- Test: one post for draft #1851 to the Models webhook from the operator's machine, 2026-10-01 13:19 EDT. Landed in #models from the operator's Slack app bot (B0C61S3J4PL) with the mention and the PR link rendered. Carrier confirmed.

## PR header rule: added 2026-10-01

- team ruling: the routine pre-populates the template header (Description written; Small change; Mixed review; AI feedback addressed; Key decisions `ML Model Update`; No UI) and leaves Author Review for him. Applied to #1852, #1853, #1854 the same day via the REST body edit. Prompt v5 carries the exact header.

## WIP title rule: added 2026-10-01

- team ruling: `WIP:` means draft. Ready PRs get plain `chore:` titles; only drafts headed for #models keep `WIP:`. Applied to #1853 and #1854 the same day; #1852 stays `WIP:` while it is a draft. Side effect: CodeRabbit had skipped every sweep PR because of the prefix, so ready PRs now get its review.

## Successor-slug rule: added 2026-10-01

- From the #prs thread on #1852: Together dropped `deepseek-ai/DeepSeek-V4-Pro` for `-0813`; the routine swapped the slug in place. the team ruled: deprecate the old provider entry and add the successor as a distinct model, so evals pinned to the old one keep their history. Rule added to the prompt (v7); a human-requested PR applying it to DeepSeek V4 Pro was opened the same day and supersedes #1852.

## Run 4: first scheduled run (2026-10-02, 07:05 America/Toronto)

- Fired on the cron at 11:05 UTC. 42 minutes wall clock, of which about 15 were lost to a first paid-test invocation that produced no output and hit the run's own 25-minute timeout; the rerun with output to a file took 4 minutes. Setup script ran at provisioning; `uv` was current; web checks passed.
- Applied the successor-slug rule unprompted: Fireworks dropped the DeepSeek V4 Pro preview slug for `-0813`, so the run added `DeepSeek V4 Pro 0813` as a distinct model on OpenRouter and Together AI (27 paid tests passed, 3 logprobs tests skipped) in a ready PR, #1871, with a plain `chore:` title and the pre-filled header. The Fireworks entry for the same checkpoint returned 404 "not deployed" on all 11 tests and on the retry, so it went to draft #1872 with a **Decisions required** section. No comments posted on either.
- Deprecation audit: nothing newly dead. Report-only findings: OpenRouter now lists `qwen/qwen3.8-max-0902` beside the old slug, which still answers; 13 OpenRouter expiries between 2026-10-08 and 2026-12-31; Fireworks router slugs return 403 from the detail API but answer chat calls.
- Remote config: `remote_config` matched `main` on all four files; a publish PR (#1859) had been merged the day before and #1810 was closed. Nothing opened.
- Slack: ready post to #prs and draft post to #models, both 07:47 EDT, both with the why. Mobile push sent.
- Behaviour to note: after the report the session unsubscribed itself from the two PRs' GitHub activity, reasoning that staying subscribed would conflict with the no-comment rule. Follow-ups on CI or reviews therefore wait for the next run.
- Also observed: a team Slack bot now posts PR cards with reviewer status in #prs for PRs that request reviewers. The sweep's PRs request none, so they get no card; requesting a reviewer from the sweep would make the webhook post redundant.

## Routine reads the skill from the branch: 2026-10-02 14:35 UTC

- The routine's message was carrying a copy of the skill text, so a commit to the PR branch changed nothing until the copy was updated by hand. Replaced with: run settings plus `git show origin/<branch>:.agents/skills/kiln-model-sweep/SKILL.md`, read it, follow it. The open PR is now the testbed: edits land on the branch, the next morning's run uses them, findings from runs go back into the branch. On merge, the branch in the message becomes `main`.

## Run 5: validation of the branch-fed routine (2026-10-02, 14:38 UTC)

- First run whose message fetched the skill from `mike/model-sweep` instead of carrying a copy. Fetch and read succeeded (115 lines), then it followed the skill: 6 minutes, 44 turns.
- Nothing new on any catalog since the morning run; four candidates failed a live call and were skipped (Together Kimi K2.6 "no deployments", Together Qwen 3.8 Flash "third-party data sharing", SiliconFlow diffusiongemma, Featherless MiMo distill "at capacity"). No backfills.
- Deprecation audit: OpenRouter no longer lists `qwen/qwen3.8-max` and Fireworks' detail API returns 403 for two router slugs; all three passed Kiln's smoke test, so nothing was marked. Report-only: six OpenRouter expiries on 2026-10-08 and 10-09, Gemini 2.5 trio on 10-20, Seed 1.6 on 11-11, GLM 4.5/4.7 on 12-31.
- Remote config: a maintainer had merged #1873 into `remote_config` at 14:18 UTC. The four source files still differed from `main` by a comment sweep, so the run generated the config from both refs, found the JSON identical, and opened nothing. That check is now in the skill.
- State it noted: #1854 merged, #1872 closed by a human, #1871 with its review thread resolved and Author Review ticked. No PR, no Slack post, one mobile push about the 10-08/10-09 expiries. Work branch deleted at the end.

## Run 6: second scheduled run (2026-10-05, 07:10 America/Toronto)

- Opened two drafts with **Decisions required**: the GPT-6 Pro trio on OpenRouter (four thinking-level tests return no reasoning text, as the shipped GPT-6 entries do) and a successor migration for Qwen 3.8 Max 0902 (the old slug carried suggested flags and a featured rank). The operator answered inside the running session: merge the GPT-6 Pro PR as is, suggest the three for evals and data gen, place each Pro above its base, check OpenAI direct (it does not serve them); on the Qwen PR, migrate the flags and the featured rank. The run applied each answer as a commit with a dated **Updates** line, marked both ready, dropped `WIP:`, and posted both to the PR channel. Now #1894 and #1895.
- A CI job failed on #1895 in an unrelated Linux tray test; the run read the log, re-ran the job once, it passed; no comment was posted.
- The session stayed subscribed to its PRs and kept waking on CI and review events, which is why it still showed as running at midday. Not a hang.
- Remote config: nothing to publish.

## Announcements: deferring to the team's PR bot (2026-10-05)

- The team's Slack bot (`Kiln-AI/nathan`, `pr_management`) posts a review card in the PR channel for any open, non-draft PR in its repos that has reviewers requested on GitHub, attributed to the author, and maintains it (status, reminders, Monday report). Source: `src/features/pr_management/refresh.ts` `wantsCard`, functional spec §4.3B. Drafts get no card, only a DM nudge to the author.
- Today #1895 had a card because a reviewer was requested; #1894 had none. The sweep's own PR-channel post duplicated the card.
- Change: the sweep requests the reviewers from its run settings on every ready PR and posts nothing in the PR channel. Drafts keep the models-channel post. The ready-for-review transition requests reviewers instead of posting. `SLACK_PRS_WEBHOOK` is no longer read. The uncommitted GitHub Action draft that labelled and announced PRs is deleted.
- Same day, follow-up ruling: the remote-config publish PR gets its card from the PR bot like any ready PR (reviewers requested), and the sweep posts nothing to Slack about it, even when it carries conflicts or a failing compatibility test.
