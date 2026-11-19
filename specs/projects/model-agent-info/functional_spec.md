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
standalone phase that runs on a machine with web access.

Revised on 2026-11-15, after an audit of the first backfill (not
committed): the note format, the tag kinds and vocabulary, and the
maintenance procedures below replace the first version. The code and skill
from the first version change to match before the backfill runs again.

Revision 2, on 2026-11-16, after an audit of the backfill: one `current`
per weight release (serving variants get `Same weights:` lines), an
explicit `recommended` bar, selection of local-only models, and a stricter
sources log. Phase 5 applies it.

Revision 3, on 2026-11-17, for sweep readiness (PR #2042 review):
`current` and a minimal note (`Description:` + `Lineup:`) are mandatory
for every new model, with no benchmark source needed. The sweep applies
tag and flag changes in its adds PR for human approval. Fully-deprecated
models lose all tags. A banned-time-words test checks notes. Stacking
on an open adds PR. `top_value` holds low- and mid-priced models only.
Rigid alias/snapshot rules replaced with judgment guidance.

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

The allowed tags are kept in code, in a new module
`libs/core/kiln_ai/adapters/model_agent_info.py`, as three maps from tag to
its info (meaning, kind and set limit):

- model tags;
- provider-entry tags (empty);
- provider-list tags (empty).

The same module holds the format rule, the limits and the note labels
below. Tests check the data against this module. `claude-maintain-models`
explains the rules and points to this module for each tag's meaning. It
does not keep its own copy of the table, so the list and its meanings exist
in one place.

### Tag kinds

Every tag is one of two kinds. The kind sets how a maintainer keeps the tag
correct, and limits the records that one edit touches.

- **Lineage tag.** There is one: `current`. It moves along a lab's line of
  models. See [The `current` tag](#the-current-tag).
- **Set tag.** Every other tag. A set tag names a short list of models that
  share a judgment, such as "the best open-weight models". Each set has a
  size limit. See [Set tags](#set-tags).

The `top_` prefix marks a set that is the best few models with a property,
not every model with it: `top_open` is not "has open weights".

The bar for a `top_` set: when an agent optimizes for that property, it
should know about this model. So `top_fast` can hold a serving variant that
is not among the fastest models overall, but is the faster way to run a
strong model; its note says so ("Not the fastest model overall, but the
faster way to run GLM 5.3.").

### The model tags

| Tag | Kind | Meaning | Limit |
|---|---|---|---|
| `current` | lineage | The lab's best offering at this price level. A model without this tag is superseded: do not choose it for a new run config unless asked. | none |
| `recommended` | set | A model we recommend as a candidate for new agents. Always also `current`. | 20 |
| `top_value` | set | Among the best quality for its cost, at a low or mid price. A top-price model is never in this set, however good its value. Look at these first when optimizing for cost. | 14 |
| `top_fast` | set | Among the fastest models for latency-sensitive work, by output speed and time to first token, or a faster hosted version of a strong model. | 14 |
| `top_on_device` | set | Among the best models that run on consumer laptops or phones. | 14 |
| `top_open` | set | Among the best open-weight models, across a range of sizes. | 14 |
| `top_writing` | set | Among the best at prose: tone, style and following a writing brief. | 14 |

The meanings above go into the tag map word for word.

The provider-entry map and the provider-list map are empty. The `tags`
fields on provider entries and provider-list items stay, for later use.

### The `current` tag

- **Price level** is a step on the lab's own ladder, as the note's
  `Lineup:` line describes it: for example Luna < Terra < Sol < Astra, or
  Haiku < Sonnet < Opus < Fable. For open-weight labs, a size class.
- Each lab has one `current` model at each price level: the newest release
  of that line, by release date, whatever its name.
- `current` is mechanical: it needs only the release date and the lab's
  product line. No benchmark source is needed.
- **Snapshots and aliases.** When a plain alias and a dated snapshot serve
  the same weights, decide with the information available and state the
  assumption in the PR body. (Revision 3; replaces the hard
  "only the alias gets the tag" rule.)
- **Unclear price levels.** When a lab's naming does not make the price
  level clear (for example, Qwen 3.8 Max versus Qwen 3.8 Max Prime),
  decide with the information available and state the assumption in the PR
  body. (Revision 3.)
- A variant that is a separate product (Pro, Omni) is a line of its own. It
  is `current` when it is the newest model of that variant line.
- **One `current` per weight release.** A serving variant serves the same
  weights as another model, under another name, for example a faster
  hosted version (GLM 5.3 Fast, Kimi K3 Fast, MiMo V2.6 Pro UltraSpeed).
  A serving variant is never `current`; only the standard model is. Both
  notes get a `Same weights:` line that names the other: "GLM 5.3 Fast is a
  faster hosted version" and "GLM 5.3 is the standard version". A serving
  variant can still be in a set other than `recommended` (for example
  `top_fast`). When the standard model is superseded, its serving variants
  get a `Superseded by:` line too.
- **When a model is added:** find the `current` model from the same lab at
  the same price level. Remove its `current` tag and add a `Superseded by:`
  line to its note. Skip this if the new model is at a different price
  level. No other records change.
- **Deprecations.** A model whose provider entries are all deprecated loses
  all its tags. A successor-slug migration moves `current` to the new
  entry. Tests skip fully deprecated models for the `Superseded by:` rule,
  and a test checks fully deprecated models have no tags. (Revision 3.)

### Set tags

- **When a model could be in a set:** (1) load the whole set; (2) decide
  whether the model joins; (3) if it joins, review every member for one
  that no longer earns its place. That can be an older model at the same
  level, or a model from any lab or level that the new model beats for the
  set's purpose. Such a member is removed only when it lost `current` or
  the set is full; otherwise it is listed as a candidate removal for a
  human. (Revision 4, 2026-11-19.)
- A set never goes over its limit. To add a model to a full set, remove the
  member with the lowest AA index inside the new model's cost band. When no
  member is inside the band, or the set has no AA numbers, a human picks.
- Every `recommended` model is also `current`. When a model loses
  `current`, it also leaves `recommended`.
- **The `recommended` bar.** `recommended` is not one model per lab or per
  level; `current` already gives that. A model is `recommended` only when
  Artificial Analysis (or, without an AA page, another independent
  benchmark) shows its quality is high for its cost, compared with the
  models across all labs at a similar cost. "The lab's flagship" or "the
  lab's smallest model" is not a reason. A model available only on local
  providers (Ollama, Docker Model Runner) is never `recommended`: an
  optimizer cannot easily test it.
- A model in a set has a note, so a reviewer can read the reason.
- Judgments that compare labs use independent data: Artificial Analysis
  first, and common sense. A lab's own release benchmarks are chosen to
  look good. They can support a claim but are never its only source.
- The PR that changes a set lists each addition to and removal from each
  set, at the top of its description.

### Tag rules

- Format: matches `^[a-z0-9_]{1,40}$`.
- At most 12 tags on one entry (a model, a provider entry, or a provider
  list item).
- No tag twice on one entry.
- A tag on a model is in the model-tag map. A tag on a provider entry is in
  the provider-entry map. A tag on a provider-list item is in the
  provider-list map. A tag in the wrong map is an error.
- A new tag is added to the right map, with its meaning, kind and limit, in
  the same change that first uses it. A new set tag that names "the best"
  of something uses the `top_` prefix.

### Note format

These apply to `agent_notes` on a model.

A note is one string of labeled lines, joined by `\n`, in this order:

| Label | Required | Content |
|---|---|---|
| `Description:` | yes | One line: what this model is. |
| `Lineup:` | yes | Its place on the lab's ladder, and what it replaced. Explains names that do not show the order. |
| `Superseded by:` | when not `current`, except on a serving variant of a `current` model | The model that replaced it, and why in a few words. Not present on a `current` model. |
| `Same weights:` | on a serving variant and on its standard model | Names the other model that serves the same weights, and how it differs: "GLM 5.3 Fast is a faster hosted version." |
| `Useful for:` | no | Cases where it is a good choice, when it is not the general pick for its level. |
| `Strengths:` | no | Its character, not its rank: "strong at agentic coding, weak at factual recall". |
| `Behavior:` | no | Settings that help or hurt, output quirks, verbosity, tool-call reliability. |
| `Deployment:` | no | Facts that change a hosting decision: dense or MoE, runs on a laptop, fits affordable GPUs. |

Each label is used at most once. A line has one or a few sentences.

**Never in a note.** Anything that Kiln or models.dev already keeps: price,
batch and cache discounts, and claims like "most expensive"; context
window and maximum output; release date and knowledge cutoff; open
weights; which providers host the model; support for function calling,
structured output or vision; the available and default thinking levels.
A note can say how the model behaves when a setting is used. It does not
say which settings exist.

**No words relative to time.** A note must not need edits as it ages. Do
not use "current", "latest", "newest", "now", "previous", "frontier",
"state of the art", "best" or "peers". To compare, name an exact model or
generation: "near Claude Opus 4.6 level, with open weights", "a step down
from GPT-6.1 Sol", "in the GPT-6.1 generation". The `current` tag and the
`Superseded by:` line, added once, are the only places that show age.

### Provider note format

These apply to `notes` on a provider-list item. The same rules, with these
labels, in this order, each optional but at least one present:

| Label | Content |
|---|---|
| `Data retention:` | Whether it logs or trains on prompts; whether a zero-retention option exists, and how to get it. |
| `Rate limits:` | How limits are set (account tier, per model); free-tier limits that break agents. |
| `Routing:` | Whether it sends requests to more than one upstream host, so output or quality can change. |
| `Gotchas:` | Setup or runtime problems: model access approval, region locks, project or quota setup. |

Never in a provider note: pricing, the models it hosts (the model list has
that) and the friendly name.

### Note rules

These apply to model notes and provider notes.

- `None` means no note. An empty or whitespace-only string is not allowed.
- At most 2,000 characters. The target is 300 to 600.
- **Minimal note is mandatory.** Every new model gets at least
  `Description:` and `Lineup:` from the lab's own model page. These two
  lines need no benchmark source. Other note lines need an independent
  source; when a maintainer cannot support a claim, they leave it out.
  (Revision 3; replaces the earlier "when nothing can be supported, the
  note stays `None`" rule.)
- A data test fails any model note containing a banned time-relative
  word from the list in `model_agent_info.BANNED_NOTE_WORDS` ("current",
  "latest", "newest", "now", "previous", "frontier", "state of the art",
  "best", "peers"), as whole words, case-insensitive. (Revision 3.)

### Approved examples

These show the format. Their facts are illustrative, not checked.
`claude-maintain-models` repeats them as models to follow.

**GPT-6.1 Terra** · tags: `current`, `recommended`
```
Description: OpenAI's mid-price general model in the GPT-6.1 generation.
Lineup: OpenAI's ladder is Luna < Terra < Sol < Astra. A large step up from GPT-6 Luna, a step down from GPT-6.1 Sol. Replaced GPT-5.6 Terra.
Strengths: Steady quality in multi-turn tool use; GPT-6.1 Sol is better on hard reasoning.
Behavior: High effort helps on hard problems; xhigh adds latency for little gain on routine tasks.
```

**GPT-5.4 Nano** · tags: none
```
Description: The smallest model in the GPT-5.4 generation.
Lineup: Below GPT-5.4 Mini.
Superseded by: GPT-6 Luna, which is stronger at a lower price.
```

**Gemini 4 Argon** · tags: `current`, `recommended`
```
Description: Google's Pro-level reasoning model in the Gemini 4 generation.
Lineup: Gemini 4 uses element names, not size names. Argon is the Pro-level model. Replaced the Gemini 3.x Pro previews.
Strengths: Strong multimodal reasoning over charts, video and documents; mixed on long autonomous coding runs.
Behavior: Very verbose: uses far more output tokens than GPT-6.1 Sol or Claude Opus 5.5 on the same tasks, so cost per task is high. Slow to the first token at high effort.
```

**Claude Haiku 5.5** · tags: `current`, `recommended`, `top_value`, `top_fast`
```
Description: Anthropic's smallest and fastest model in the 5.5 generation.
Lineup: Anthropic's ladder is Haiku < Sonnet < Opus < Fable. A large step down from Claude Sonnet 5.5.
Useful for: Subagents, routing, classification and extraction at high volume.
Behavior: Reliable tool calls for its size; quality drops on long multi-step reasoning.
```

**Mistral Large 4** · tags: `current` (not `recommended`)
```
Description: Mistral's open-weight flagship of the Large 4 generation.
Lineup: Mistral's ladder is Ministral < Small < Medium < Large. Replaced Mistral Large 3.
Useful for: Teams that need a European lab.
Strengths: Strong at coding and terminal tasks; near GPT-5.6 Terra level on general intelligence.
```

**Qwen 3.8 27B** · tags: `current`, `top_open`
```
Description: Qwen's dense mid-size open-weight model in the 3.8 generation.
Lineup: Below the Qwen 3.8 2.4T A95B open MoE. The closed Qwen 3.8 Max and Flash API models are a separate line.
Useful for: Self-hosted or on-prem work where you manage your own GPUs.
Strengths: Close to Gemma 4 31B at reasoning and coding.
Deployment: Dense, so it runs on one affordable GPU more easily than MoE models of similar quality.
```

**Gemma 4 2B** · tags: `current`, `top_on_device`
```
Description: The smallest open-weight model in Google's Gemma 4 generation.
Lineup: Gemma 4 sizes are 2B < 4B < 27B MoE < 31B dense. Gemma is Google's open-weight line, separate from Gemini.
Useful for: Local or on-device agents, when data must stay on the machine.
Behavior: Follows simple instructions well; unreliable at multi-step tool use.
Deployment: Runs on consumer laptops and high-end phones.
```

**OpenRouter** (provider note)
```
Data retention: Depends on the upstream host. Account settings can block hosts that log or train on prompts.
Routing: Routes each request to one of several upstream hosts; quality and quantization can differ between them.
Gotchas: Some models are free variants with low rate limits; do not use them for production agents.
```

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

- A section on agent notes and tags that holds:
  - the note format, the "never in a note" list, the rule against words
    relative to time, and the approved examples above, word for word;
  - the provider note format;
  - the two tag kinds, and that each tag's meaning, kind and limit are in
    the tag map;
  - the `current` procedure and the set-review procedure, step by step, as
    above;
  - the rule on sources: Artificial Analysis first for comparisons across
    labs, a lab's own release claims as support only, and common sense;
  - how to add a tag, and that an unsupported claim is left out.
- Phase 3 (code changes) gets a step for each new model: write its note and
  tags, run the `current` procedure for its lab and price level, and run
  the set-review procedure for each set it could join. A run with nobody
  watching (the scheduled model sweep) follows the same rules. The set
  review is required: it fetches the model's Artificial Analysis page,
  compares it with same-day AA pages of every `current` model within a
  1.5x cost band, members and non-members, and writes a **Set review** section in the PR even when no
  set changes. Removals other than a lost `current` or a full set are
  listed as candidates for a human, not applied. Without an AA page,
  `recommended` needs another independent benchmark, `top_value` is
  skipped, and `top_fast` takes only a faster serving of a strong model; `top_open`, `top_on_device` and `top_writing` use
  their own evidence. (Revision 4, 2026-11-19.)
- A data test (`test_live_models_have_notes`) fails any live model without
  a note, except the older models frozen in `MODELS_WITHOUT_NOTES`, which
  only shrinks. (Revision 4, 2026-11-19.)
- The PR description: when a set changes, a section at the top lists each
  addition and removal, per set, with a short reason for each.
- "Adding a Net-New Provider": the touchpoint checklist replaces the
  `provider_name_from_id` item with a provider-list item: id, friendly name,
  `models_dev_id` (checked against models.dev, or `None`), and notes and
  tags when they can be supported. "Friendly names everywhere" names the
  provider list instead of `provider_name_from_id`.

Other guidance that the change makes stale is updated in the same change,
found with the `docs-sync` skill. Known items:

- `kiln-model-sweep`: its check for a remote-config publish diffs a list of
  files. `ml_provider_list.py` joins that list. Its PR description puts set
  changes at the top, as above.
- `kiln-conventions` (`references/core.md`): the "Where things go" table and
  the provider touchpoint list name the provider list.

## Tests

Data tests, on the built-in lists:

- Every model tag, provider-entry tag and provider-list tag follows the tag
  rules: format, count, no duplicates, in the right map.
- Every `agent_notes` and provider `notes` follows the note rules: `None`
  or a non-blank string of at most 2,000 characters.
- Every key of the three tag maps follows the format rule, and every
  meaning is a non-blank string. The model map has exactly one lineage tag,
  `current`, with no limit. Every set tag has a limit.
- Each set tag is on no more models than its limit.
- Every model tagged `recommended` is also tagged `current`.
- Every model with a tag has a note.
- Every model note follows the note format: the first line starts with
  `Description:`; every line starts with a known label; labels are in the
  table's order and each is used at most once; `Lineup:` is present.
- A `current` model has no `Superseded by:` line. A model with a note that
  is not `current` has a `Superseded by:` line or a `Same weights:` line
  (a serving variant of a `current` model). Fully deprecated models
  (all provider entries deprecated) are skipped for this rule.
- A model whose provider entries are all deprecated has no tags.
- No model note contains a banned time-relative word from
  `model_agent_info.BANNED_NOTE_WORDS`.
- Every provider note uses only the provider labels, in order, each at most
  once.
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
any entry is not selected, unless it is featured or local-only (below).

**Local-only models.** A model whose entries that are not deprecated are
all on local providers (Ollama, Docker Model Runner) has no models.dev
match. It is selected when the lab's model card (Hugging Face or the lab's
own page) gives a release date within the same 12 months. These models are
selected mainly so they can be judged for `top_on_device` (and `top_open`);
they are hard to experiment with, so they are never `recommended`, and
their notes can be short.

Labs that stopped publishing are not backfilled: a lab with no selected
model gets no `current` tags.

### Tags in the backfill

- `current`: for each lab, for each price level, the one model the
  `current` rules pick, among the selected models.
- Each set is built as one review across all selected models, not model by
  model, and stays within its limit.
- No provider-entry tags and no provider-list tags.

### What else

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
  `specs/projects/model-agent-info/backfill_sources.md`, so a reviewer can
  answer "why is this here?" without redoing the research:
  - **Per set:** one row per member with the AA intelligence index, AA
    cost per task (or blended price when AA has no cost per task), AA
    output speed, and the AA page URL. A member with no AA page cites the
    URL of the source used instead. The reason column states the
    comparison ("index 52 at $1.10/task; next best at that cost is 44"),
    not a description ("strong flagship").
  - **Per model:** the source URL behind each line of its note other than
    `Description:` and `Lineup:` when those come from the lab's own model
    page, which is cited once.
  - **Per provider:** the source URL behind each line of its note.
  - Every figure in the log is checked against its source; a price is
    labeled input or output.
- The PR description lists the members of each set at the top.
- The data tests pass.

## Out of scope

As the overview lists, and also:

- Loading `provider_list` in Kiln clients.
- The web UI's provider name map.
- Moving `KILN_TO_MODELS_DEV_PROVIDER` in the Kiln server to the published
  list. The Kiln server is another repository.
- Publishing: the existing process publishes the file after merge, through
  a pull request from `main` to the `remote_config` branch.
