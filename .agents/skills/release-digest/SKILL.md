---
name: release-digest
description: Post a "what's changed since the last release" recap to the release Slack channel for final QA. Groups merged PRs by author and classifies each as feature / bug fix / task. Use when the user wants a release recap, a changelog since the last tag, or to prep QA before cutting a release from main.
---

# Release Digest

Build a human-readable recap of everything merged to `main` that is **not yet in the
latest release tag**, and post it to the team's release Slack channel for final QA.

The recap is grouped **by author** and each change is classified as **feature**,
**bug fix**, or **task**. This is on-demand: run it when someone asks for a release
recap or wants to QA before cutting a release.

> Linear ticket tracking ("which tickets are targeted for this release") is **out of
> scope for now** — punted to a later iteration. This skill only covers what's changed.

---

## Phase 1 — Gather the change set

Run the gather script from the repo root. It fetches tags + `origin/main`, finds the
latest tag, and lists every merged PR in the range `<last_tag>..origin/main`:

```bash
python3 .agents/skills/release-digest/scripts/gather_changes.py > /tmp/release_digest.json
```

Key design point: it uses the **git commit range** as the source of truth, not merge
dates. A PR merged the same day a tag was cut can already be in that release, so a
date filter would over-report. Trust the range.

**Pre-release / already-cut releases.** By default the baseline is the newest tag
(`git describe`). But if the release you're QA'ing has **already been tagged** — it's a
pre-release still being validated, so `main` is already even with it — the default
range is empty. In that case pass `--pre-release`, which steps the baseline back one
tag so the range recaps exactly what went *into* the pre-release:

```bash
python3 .agents/skills/release-digest/scripts/gather_changes.py --pre-release > /tmp/release_digest.json
```

Signs you want `--pre-release`: the first run reports "nothing unreleased" or "main is
even with the latest tag", yet the user says a release was just cut / is being QA'd. To
name the baseline explicitly instead, use `--since <tag>` (e.g. `--since v1.0.3`). The
two flags are mutually exclusive. When `--pre-release` is used, the newest tag is the
one being cut, so in Phase 3 use **that tag** as `<new_release>` rather than asking.

The JSON contains:
- `last_tag` — the most recent release (e.g. `v1.0.3`)
- `head_ref` — `origin/main` (or `main` if no remote ref)
- `pr_count`, `commit_count`
- `prs[]` — `{number, title, author_name, author_login, url, labels, additions, deletions, body}`
- `direct_commits[]` — teammate commits pushed straight to main, no PR — `{sha, title, author_login, author_name}`
- `excluded_prs[]` — PRs/commits from non-teammates, dropped from the recap. PR entries
  have a `number`; direct-commit entries have `number: null` and rely on `title`.
- `unresolved_prs[]` — PRs whose `gh pr view` failed (`{number, error}`). If non-empty,
  the change set is partial — tell the user which PRs couldn't load before posting.

Only the five teammates in the script's `TEAM` map (Sam, Leonard, Daniel, Mike,
Steve) are included in the recap. PRs from anyone else are filtered into
`excluded_prs` rather than itemized. To add a teammate, edit `TEAM` in the script.

**If `pr_count` is 0 AND `direct_commits` is empty:** tell the user `main` is even with
`<last_tag>` — nothing to QA or release yet. Do not post to Slack. Stop here. (Direct
commits alone, with no PRs, still count as unreleased changes worth a digest.)

---

## Phase 2 — Classify and group

Read `/tmp/release_digest.json`. Treat every item in `prs[]` **and** `direct_commits[]`
as a change to recap (direct commits are real work that shipped — just with no PR
number). Classify each into one of three buckets:

- **Feature** — a substantive *new product capability*: new UI, a new endpoint, a new
  tool, new eval/RAG/fine-tune functionality, or a meaningful enhancement to how the
  product works. Reserve this for things a user would notice as "Kiln can now do X."
- **Bug fix** — corrects broken or incorrect behavior: regressions, crashes, hangs,
  wrong output, security fixes.
- **Task** — everything that is *neither* a substantive new capability *nor* a fix to
  broken behavior: refactors, docs/README, tests, CI/build, dependency bumps, version
  bumps, chores, internal flags, code removal/cleanup — **and routine model-catalog
  work** (see below). Matches Linear's "Task" issue type: maintenance/internal work.

**Adding models is a Task, not a Feature.** Kiln ships new model and provider entries
constantly — "Add <model> to model list", "Add <provider> for <model>", backfilling a
model on a provider, re-enabling/un-recommending a model, version bumps to a model
entry. These are catalog/config maintenance, so they go in **Task** even though the
title starts with `Add`/`Enable`. Only promote to **Feature** if the PR adds a genuinely
new *capability* around models (e.g. a new thinking-level control, a new extraction
modality, a new provider *integration type*) rather than just registering a model_id.

**Decision order** (use the first signal that's decisive):
1. **PR labels** — `bug`/`fix` → Bug fix; `feature`/`enhancement` → Feature;
   `chore`/`docs`/`refactor`/`ci` → Task. (Kiln PRs are usually unlabeled, so this
   rarely fires — fall through to the title.)
2. **Model-catalog check** — if the change just registers/edits model or provider
   entries (not new behavior), it's a **Task**, regardless of the `Add`/`Enable` verb.
3. **Conventional-commit / verb prefix in the title** — `fix:`/`Fix ` → Bug fix;
   `feat:`/`Add `/`Enable ` (a new *capability*) → Feature; `chore:`/`refactor:`/`ci:`/
   `docs:`/`Bump `/`Remove `/`Deprecate `/`Version bump` → Task.
4. **What the change does** (read the title, and `body` if still unclear) — ask "does
   this give the user a genuinely new capability (Feature), fix something that was
   broken (Bug fix), or is it routine/maintenance (Task)?"

**"Task" is the residual bucket**, not a guess: a change lands there only because it
is positively *not* a new capability and *not* a fix — e.g. `Deprecate Models`,
`min age for dependencies`, `Version bump`, `new draft readme`, `fix typos`. When a
change is genuinely ambiguous between Feature and Bug fix, prefer the one the title
leans toward; only fall to Task when it's truly neither. This is a judgment call made
per item — surface it to the user before posting so they can re-bucket anything.

Then **group by author** (`author_name`). Within each author, list changes by PR
number, newest first; put any direct commits (no PR number) last. The feature / fix /
task split is **not** shown per line — it only feeds the tally at the bottom.

---

## Phase 3 — Compose the Slack message

**First, get the new release name** — the version being cut (e.g. `v1.0.4`). If you ran
in `--pre-release` mode, the release has already been tagged, so use that newest tag
(the one the script named as "the release being QA'd") as `<new_release>` — no need to
ask. Otherwise the release isn't tagged yet and can't be derived from git, so **ask the
user**. Use the result as `<new_release>` in the title.

Use this shape (Slack mrkdwn — `*bold*`, not `**bold**`):

```
:rocket: *v1.0.4 Release Status* :rocket:

*12 changes since v1.0.3*
_<one-to-two sentence plain-English recap of the headline changes>_

*Daniel Chiang*
• Add deprecated flag to embedding models (#1466)
• Add deprecated flag to reranker models (#1465)

*Sam Fierro*
• Dedup frozen prompts and bake type into their name (#1501)

*Steve Cosman*
• Add Jinja2 input transform on RunConfigs (#1433)
• Version bump in lock and desktop app version check

:bar_chart: *7 features · 3 fixes · 2 tasks*

:information_source: _1 PR from a non-teammate: #1456 (ianjamesburke)._
```

Rules:
- **Header:** `:rocket: *<new_release> Release Status* :rocket:`, then a blank line.
- **Change count** on its own line, **bold**: `*<N> changes since <last_tag>*`.
- **Recap paragraph** immediately under it, wrapped in **italics** (`_..._` around the
  whole paragraph) — the "what did we do" summary in plain English, not just a list.
  Compose it so the italics survive: write it as **a single line with no hard line
  breaks** (wrap is fine, but don't insert `\n` mid-paragraph — newlines break the
  italic span in Slack), and use **no literal `_` anywhere inside** (an underscore
  would close the italics mid-paragraph — rewrite e.g. `snake_case`/`model_id` or any
  underscored identifier without it).
- One **bullet** per change, no per-line emoji: `• <title> (#<number>)`. Keep the
  title; trim trailing noise.
- **Direct commits have no PR number** — render them as `• <title>` with nothing in
  parentheses (e.g. `• Version bump`). List them under their author, after the PRs.
- Within each author, list newest PR first; direct commits last. Don't print the
  feature/fix/task bucket per line.
- **Summary block** at the end, in this order:
  1. A **bold** `:bar_chart:` tally line: `:bar_chart: *<X> features · <Y> fixes · <Z> tasks*`.
  2. A blank line.
  3. If `excluded_prs` is non-empty, an **italic** `:information_source:` line noting the
     excluded non-teammate changes (so the omission is visible, not silent). Reference a
     PR entry by `#<num>` and a direct-commit entry (where `number` is null) by its
     `title` — never print `#None`. E.g.
     `:information_source: _<N> change(s) from non-teammates excluded: #1456 (ianjamesburke)._`
- Link the PR numbers if easy (`<url|#1501>`), but plain `#1501` is fine — keep it readable.

**Show the composed message to the user and get confirmation before posting** (it's an
outward-facing post to a shared channel).

---

## Phase 4 — Post to Slack

Post to **`#release`** (channel ID `C0BDGTGBL4Q`) — the team's release channel. This is
the default target; only post elsewhere if the user explicitly names a different
channel. (If the ID ever fails to resolve, fall back to `slack_search_channels` with
query `release` to re-find it.)

Only post after the user has confirmed the composed message in Phase 3. Post with
`mcp__claude_ai_Slack__slack_send_message`. After posting, give the user the channel
name and a link/confirmation.

---

## Checklist

- [ ] Gather script run; `/tmp/release_digest.json` written
- [ ] If `pr_count` is 0, reported "nothing unreleased" and stopped
- [ ] Asked the user for the new release name (used in the title)
- [ ] Each PR classified (feature / bug fix / task)
- [ ] Grouped by author, recap paragraph written
- [ ] Message shown to user and confirmed
- [ ] Posted to #release (C0BDGTGBL4Q); confirmation returned to user
