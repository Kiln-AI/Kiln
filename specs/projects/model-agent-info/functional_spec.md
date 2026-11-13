---
status: complete
---

# Functional Spec: Model Agent Info

The overview ([project_overview.md](project_overview.md)) says what and why.
This spec pins down the behavior, the contracts and the answers to the
overview's open questions.

## Summary

Kiln's published model file (`kiln_config_v2.json`) gains:

1. On each model: `agent_notes` and `tags`.
2. On each provider entry of a model: `tags`.
3. At the top level: `provider_list`, one item per `ModelProviderName`.

The data is written by maintainers (people, or agents running
`claude-maintain-models`). Agents outside Kiln read it, Harness Tuner first.
Nothing in Kiln reads the new data in this project, except that the
friendly provider names move into the provider list and
`provider_name_from_id` reads them from there.

The work ships in two parts. The code, tests and skill changes come first,
with the new fields empty. The backfill of notes and tags comes last, as a
standalone phase that runs on another machine.

## Decisions on the overview's questions

### Where the provider list lives

- A new module beside the model list:
  `libs/core/kiln_ai/adapters/ml_provider_list.py`. It holds the
  `KilnProviderInfo` model and the built-in list. `ml_model_list.py` is over
  12,000 lines and is about models; providers are a separate list with a
  separate shape, like the embedding and reranker lists.
- The publish writes it. Kiln clients do not load it. `KilnRemoteConfig`
  does not change, and `deserialize_config_data` ignores the key, as it does
  today for any key it does not know.
  - Why: nothing in Kiln reads provider notes yet. Loading them would add a
    second list that the background refresh replaces at runtime, with its
    locking and tests, for no reader. When the Kiln assistant needs the
    notes, loading the key is a small, separate change.
  - So there are two copies. The copy in the code (`built_in_providers`)
    ships with each release, and Kiln reads it for friendly names through
    `provider_name_from_id`. The copy in the published file is for outside
    readers only. A change to a provider's notes reaches outside readers at
    the next publish; a change to a friendly name reaches Kiln users at the
    next release, as today.

### Friendly names

- The provider list is the one source of friendly provider names in
  Python. `provider_name_from_id` looks the name up in the list. Its
  signature, its return values and its handling of an unknown id do not
  change.
- The web UI's own name map (`provider_name_map` in
  `app/web_ui/src/lib/stores.ts`) does not change. The web UI is out of
  scope.
- A new provider then needs its friendly name in one Python place, not two.
  The type checker no longer catches a missing name (it did through the
  exhaustive `match`); a test does instead (see Tests).

### Which tests keep the data correct

See [Tests](#tests).

## The vocabulary: tags and notes

### Where the tag list is kept

The allowed tags and their meanings are kept in code, in a new module
`libs/core/kiln_ai/adapters/model_agent_info.py`, as three maps from tag to
meaning:

- model tags;
- provider-entry tags;
- provider-list tags (empty at the start).

The same module holds the format rule and the limits below. Tests check the
data against this module. `claude-maintain-models` explains the rules and
points to this module for the list. It does not keep its own copy of the
table, so the list and its meanings exist in one place.

This differs from the overview in one detail: the overview has the skill
document each tag. The skill still tells the maintainer what each tag means
and how to add one, by sending them to the module. A second copy in the
skill would drift.

### Tag rules

- Format: matches `^[a-z0-9_]{1,40}$`.
- At most 12 tags on one entry (a model, a provider entry, or a provider
  list item).
- No tag twice on one entry.
- A tag on a model is in the model-tag map. A tag on a provider entry is in
  the provider-entry map. A tag on a provider-list item is in the
  provider-list map. A tag in the wrong map is an error, for example
  `fast` on a model.
- A new tag is added to the right map, with its meaning, in the same change
  that first uses it. Its meaning is a claim compared with models at the
  same price, and one the maintainer would stand behind.

The starting model tags and provider-entry tags are the overview's table,
with its meanings word for word.

### Note rules

These apply to `agent_notes` on a model and to `notes` on a provider-list
item.

- `None` means no note. An empty or whitespace-only string is not allowed.
- At most 2,000 characters. The target is a few sentences.
- Content: as the overview's "What goes in `agent_notes`" says. Provider
  notes cover data retention, rate limits, routing and gotchas.
- A note states only what a maintainer can support from the provider's
  documentation, a public benchmark, or Kiln's own tests. When a maintainer
  cannot support a claim, they leave it out. When nothing can be supported,
  the note stays `None` and the tags stay empty.

### No validation at parse time

`KilnModel`, `KilnModelProvider` and `KilnProviderInfo` do not validate tags
or notes. A tag is any string and a note is any string or `None`. The rules
above are enforced by tests on the built-in data only.

Why: the published file reaches clients of every release. If a client
validated tags against its own list, a tag added later would make that
client drop the whole model. Tests stop a bad value before it is published,
and an old client stays tolerant.

## Contracts

### `KilnModel`

| Field | Type | Default |
|---|---|---|
| `agent_notes` | `str \| None` | `None` |
| `tags` | `list[str]` | empty list |

The docstring says that `agent_notes` is for an agent that chooses or
configures the model, such as the Harness Tuner optimizer or the Kiln
assistant, and that `editorial_notes` is for people in the Kiln UI. It says
that `tags` are true of the model on every provider.

### `KilnModelProvider`

| Field | Type | Default |
|---|---|---|
| `tags` | `list[str]` | empty list |

The docstring says that these tags are true of this provider entry only.

### `KilnProviderInfo`

| Field | Type | Default |
|---|---|---|
| `id` | `ModelProviderName` | required |
| `friendly_name` | `str` | required |
| `notes` | `str \| None` | `None` |
| `tags` | `list[str]` | empty list |
| `models_dev_id` | `str \| None` | `None` |

The built-in list has one item per `ModelProviderName`, in the order the
enum declares them. The friendly names are the current return values of
`provider_name_from_id`. The `models_dev_id` values are the overview's
table. `notes` and `tags` start empty.

### The published file

`provider_list` is a JSON array at the top level, beside `model_list`,
`embedding_model_list` and `reranker_model_list`. Each item is the item's
`model_dump(mode="json")`: an object with exactly the keys `id`,
`friendly_name`, `notes`, `tags` and `models_dev_id`. `id` is the enum's
string value. A `None` is `null`. An empty tag list is `[]`.

Each model object gains `agent_notes` and `tags`. Each provider-entry object
gains `tags`. Nothing else in the file changes.

### Compatibility

- The current client loads the new file: it ignores `provider_list`, and it
  reads the new fields as data no Kiln code uses.
- kiln-ai 0.19.0 loads the new file. The backward-compatibility test
  (`test_backwards_compatibility_with_v0_19`) shows this and must pass
  before the change merges.
- A file from before this project loads in the new client: the new fields
  take their defaults.

## The maintenance skills

`claude-maintain-models` changes as the overview's "The maintenance skill"
section says, with these details:

- A new section on agent notes and tags: what goes in a note and what does
  not, the tag rules, where the tag list is kept, how to add a tag, and the
  rule that an unsupported claim is left out.
- Phase 3 (code changes) gets a step to fill `agent_notes` and model `tags`
  for each new model, and `tags` for each new provider entry, under the
  note rules. A run with nobody watching (the scheduled model sweep) follows
  the same rule: when nothing can be supported, it leaves the fields empty
  and says so in the PR.
- "Adding a Net-New Provider": the touchpoint checklist replaces the
  `provider_name_from_id` item with a provider-list item: id, friendly name,
  `models_dev_id` (checked against models.dev, or `None`), and notes and
  tags when they can be supported. "Friendly names everywhere" names the
  provider list instead of `provider_name_from_id`.

Other guidance that the change makes stale is updated in the same change,
found with the `docs-sync` skill. Known items:

- `kiln-model-sweep`: its check for a remote-config publish diffs a list of
  files. `ml_provider_list.py` joins that list.
- `kiln-conventions` (`references/core.md`): the "Where things go" table and
  the provider touchpoint list name the provider list.

## Tests

Data tests, on the built-in lists:

- Every model tag, provider-entry tag and provider-list tag follows the tag
  rules: format, count, no duplicates, in the right map.
- Every `agent_notes` and provider `notes` follows the note rules: `None`
  or a non-blank string of at most 2,000 characters.
- Every key of the three tag maps follows the format rule, and every
  meaning is a non-blank string.
- The provider list has exactly one item per `ModelProviderName`, in enum
  order. Every friendly name is non-blank. Every `models_dev_id` is `None`
  or matches `^[a-z0-9-]+$`.

Behavior tests:

- `provider_name_from_id` returns the list's friendly name for every
  `ModelProviderName`, and keeps its current result for an unknown id. The
  existing tests of it keep passing unchanged.
- The serialized config has `provider_list` with one item per provider and
  exactly the five keys per item, and the new model and provider-entry
  fields.
- `deserialize_config_data` loads a file with `provider_list` and the new
  fields, and a file without them.
- A model or provider entry with an unknown tag still loads from the remote
  config. This guards the no-validation rule.
- `test_backwards_compatibility_with_v0_19` passes. It needs `uv` and
  network access to PyPI, and runs only with `KILN_TEST_COMPATIBILITY=1`.

## The backfill

The overview's "The backfill" section, made exact. It runs last, as its own
phase, on a machine with web access. It changes data only: no code, no
tests, no skill.

### Which models

A model gets `agent_notes` and model tags when either is true:

- it has a `featured_rank`;
- it has at least one provider entry that is not deprecated, and models.dev
  gives a release date within 12 months before the day the backfill runs.

To find a release date: for each provider entry that is not deprecated, look
up models.dev under the provider's `models_dev_id` and the entry's
`model_id`. Use the earliest `release_date` found. A model with no match on
any entry is not selected, unless it is featured.

### What else

- Provider-entry tags (`fast`, `very_fast`) on the selected models' entries
  that are not deprecated, where the provider's documentation or a public
  benchmark supports them.
- `notes` for every provider-list item that a person can connect: every
  item except `kiln_fine_tune` and `kiln_custom_registry`.
- The `huggingface` `models_dev_id`: set it to `huggingface` only after
  checking that models.dev's `huggingface` entry is the same service Kiln
  calls (Hugging Face Inference Providers). Otherwise leave it `None`.

### Rules

- The note rules and tag rules above. A claim with no source is left out.
- `editorial_notes`, `featured_rank` and every other existing field stay as
  they are.
- A sources log is committed with the data, at
  `specs/projects/model-agent-info/backfill_sources.md`. For each model and
  provider it lists the sources behind the note and each tag, so a reviewer
  can check a claim without redoing the research.
- The data tests pass.

## Out of scope

As the overview lists, and also:

- Loading `provider_list` in Kiln clients.
- The web UI's provider name map.
- Moving `KILN_TO_MODELS_DEV_PROVIDER` in the Kiln server to the published
  list. The Kiln server is another repository.
- Publishing: the existing process publishes the file after merge, through
  a pull request from `main` to the `remote_config` branch.
