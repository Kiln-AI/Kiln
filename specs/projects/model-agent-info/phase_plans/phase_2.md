---
status: complete
---

# Phase 2: Skills and guidance

## Overview

Phase 1 added agent notes and tags to the model list, a provider list in
`ml_provider_list.py`, and `provider_list` in the published file. This
phase updates the agent guidance so maintainers fill the new fields and keep
the provider list current, and fixes the docs that Phase 1 made stale. It
changes docs and skills only: no code, no tests, no data.

## Steps

1. `.agents/skills/claude-maintain-models/SKILL.md`:
   - Frontmatter `description`: also trigger when the user wants to write
     or fix agent notes or tags for a model, a provider entry or a provider.
   - Intro list of what a new model needs: add agent notes and tags.
   - Phase 3: new subsection "3g. Agent notes and tags" after 3f, one short
     paragraph: fill `agent_notes` and model `tags` for each new model and
     `tags` for each new provider entry, by the rules in the new section;
     leave them empty when nothing can be supported, and say so in the PR.
     (The architecture says "after 3b"; 3c–3f already follow 3b, so it goes
     at the end of Phase 3 to keep the numbering.)
   - New top-level section "Agent notes and tags", after Phase 3 and before
     Phase 4. Contents: who reads the fields (the published file, agents
     such as Harness Tuner and the Kiln assistant), and the contrast with
     `editorial_notes`; what goes in `agent_notes` and what does not (the
     overview's lists); provider-list `notes` content; the note rules (None
     or non-blank, at most 2,000 characters, a few sentences); the source
     rule (a claim only from provider docs, a public benchmark or Kiln's own
     tests; else leave it out, the PR says so); the tag rules (format, 12
     per entry, no duplicates, the right map); that the tag list and
     meanings live in `libs/core/kiln_ai/adapters/model_agent_info.py`, read
     there, not copied; how to add a tag (right map with its meaning, update
     `test_starting_tags` in `test_model_agent_info.py`, same change); no
     parse-time validation, tests check the data; the test command.
   - Checklist: one item for agent notes and tags.
   - "Adding a Net-New Provider", libs/core touchpoints: drop
     `provider_name_from_id` from the `provider_tools.py` item (two spots
     left), and add an item for `built_in_providers` in `ml_provider_list.py`:
     id in enum order, friendly name, `models_dev_id` checked against
     models.dev or `None`, notes and tags when they can be supported.
   - "Friendly names everywhere": the Python name map is the provider list;
     a test (`test_one_item_per_provider_in_enum_order`), not pyright, catches
     a missing item; TypeScript still forces the web map.
   - Release-gating rule: the provider-list item is plumbing (PR 1). It is
     published in the remote config, but only for outside agents.
2. `.agents/skills/kiln-model-sweep/SKILL.md`:
   - Remote config publish check: add `ml_provider_list.py` to the diffed
     files; the publish PR body lists provider-list changes too.
   - Pre-answered gates: one line on agent notes and tags. Fill them per
     `claude-maintain-models`; leave empty when unsupported and say so in
     the PR; never add a tag in a sweep (that changes another file), put a
     proposed tag under **Decisions required** instead.
3. `.agents/skills/kiln-conventions/references/core.md`:
   - "Where things go": a row for provider facts and friendly names:
     `adapters/ml_provider_list.py`; a row for the agent tag vocabulary:
     `adapters/model_agent_info.py`.
   - "Adding a provider": item 3 names only `provider_warnings`; a new item
     for the `built_in_providers` item in `adapters/ml_provider_list.py`.
   - Model list gotcha: `built_in_providers` is a tuple fixed at release,
     not refreshed from the remote config.
4. Run the `docs-sync` skill's searches for every changed path, symbol and
   behaviour from Phase 1, read each hit, and fix any other stale statement.

## Tests

- No new tests: this phase changes docs only.
- Re-run the data tests the docs point to
  (`test_model_agent_info.py`, `test_ml_provider_list.py`,
  `test_ml_model_list.py`) to confirm the commands in the docs work.
- Run `uv run ./checks.sh --agent-mode` (or its parts) to confirm nothing
  else broke, and `misspell` on the changed files.
