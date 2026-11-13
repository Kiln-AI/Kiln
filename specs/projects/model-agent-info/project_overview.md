---
status: draft
---

# Model Agent Info

Add notes and tags for agents to Kiln's model list, and a list of
providers. Agents that choose or configure a model read them from the
published file.

This overview was written in the Harness Tuner repository, as phase 1 of
its project `model-provider-info`, on 2026-11-13. The facts below were
checked against Kiln `main` at commit `a1dc3e4` and the models.dev file of
the same day. Start this project with `/spec new_project` as
`model-agent-info`.

## Why

Harness Tuner improves an AI agent by changing its harness: the prompt, the
model, the tools and the settings. Its loop agents choose models and
providers. Today they get a list of model names, the thinking levels and
one output mode. That is not enough to choose with.

Harness Tuner will read two public files at the start of each run:

- **Kiln's published model file**, for what Kiln knows: which models work
  in Kiln, on which providers, with which settings, and what Kiln
  recommends.
- **models.dev** (`https://models.dev/api.json`), for the facts that an
  outside source already keeps: price, context window, maximum output,
  release date, knowledge cutoff, open weights and reasoning.

This project adds to the first file the data that only Kiln can give: notes
written for an agent, labels that code can filter on, and notes about each
provider. Other agents can use the same data later, for example the Kiln
assistant.

## Background in this repository

- `libs/core/kiln_ai/adapters/ml_model_list.py` has `KilnModel`,
  `KilnModelProvider` and `built_in_models`.
- `libs/core/kiln_ai/adapters/remote_config.py` serializes the lists.
  `serialize_config` writes `model_list`, `embedding_model_list` and
  `reranker_model_list` with `model_dump(mode="json")`.
- `.github/workflows/publish_remote_config.yml` publishes
  `kiln_config_v2.json` to `https://remote-config.getkiln.ai/` on a push to
  the branch `remote_config`. Clients load it over the air between
  releases.
- The workflow runs `test_backwards_compatibility_with_v0_19` first. That
  test parses the current file with kiln-ai 0.19.0.
- `deserialize_config_data` reads each top-level key with `.get`, and
  validates each model and each provider entry alone. `KilnModel` and
  `KilnModelProvider` use Pydantic's default `extra="ignore"`. So the
  current client ignores a new optional field and a new top-level key. The
  backward-compatibility test is the check that v0.19 does too.
- `editorial_notes` is short text for people. The models page of the web UI
  shows it (`app/web_ui/src/routes/(app)/models/+page.svelte`). 59 models
  have it. 13 models have a `featured_rank`.
- `.agents/skills/claude-maintain-models/SKILL.md` is the skill that adds
  new models and providers to `ml_model_list.py`.

## The new fields

Each field is optional and has a default, so an older client ignores it.

| Field | On | Type | Purpose |
|---|---|---|---|
| `agent_notes` | `KilnModel` | `str \| None`, default `None` | Notes for an agent that chooses or configures the model, such as the Harness Tuner optimizer or the Kiln assistant. The docstring says this. |
| `tags` | `KilnModel` | `list[str]`, default empty | Short labels that code can filter on. True of the model on every provider. |
| `tags` | `KilnModelProvider` | `list[str]`, default empty | Labels true of one provider entry only, for example speed. |
| `provider_list` | the published file, top level | list of `id`, `friendly_name`, `notes`, `tags`, `models_dev_id` | Notes about each provider, and the one map from Kiln's provider ids to models.dev. |

`editorial_notes` does not change. It stays short text for the Kiln UI.

### What goes in `agent_notes`

Write for an agent that compares this model with others at the same price.

- Strengths and weaknesses compared with models at the same price.
- The settings it responds to, for example a thinking level that helps or
  that adds cost for no gain.
- Output quirks, for example long answers or a fixed preamble.
- Tool-call reliability.
- When it matters, the model that replaces it.

Do not put these in `agent_notes`: price, context window, maximum output,
release date, knowledge cutoff, open weights. models.dev gives them, and two
copies get out of date.

Keep each note short. A few sentences is the target. Harness Tuner cuts a
note over 2,000 characters.

## Tags

A tag is lower case letters, digits and `_`, at most 40 characters. An
entry has at most 12 tags. Harness Tuner drops a tag that does not follow
this rule.

The starting tags:

| Tag | On | Meaning |
|---|---|---|
| `very_fast` | provider entry | Output speed is much higher than usual for a model of this size, usually on special hardware. |
| `fast` | provider entry | Output speed is higher than usual for a model of this size and price. |
| `best_value` | model | Its quality for its price is among the best at that price. |
| `strong_agentic` | model | Reliable in multi-step tool use and agent loops, compared with models at the same price. |
| `strong_coding` | model | Strong at writing and fixing code, compared with models at the same price. |
| `strong_writing` | model | Strong at prose: tone, style and following a writing brief, compared with models at the same price. |
| `verbose` | model | Its answers are usually longer than asked, or longer than those of similar models. |

`claude-maintain-models` documents each tag with this meaning.

The rule for a new tag:

- lower case and `_`;
- a claim the maintainer would stand behind, compared with models at the
  same price;
- documented in the skill before it is used.

There are no starting tags for the provider list. A tag there follows the
same rule.

## The provider list

A new top-level key `provider_list` in the published file. Each item:

| Field | Type | Meaning |
|---|---|---|
| `id` | str | Kiln's provider id, a `ModelProviderName` value. |
| `friendly_name` | str | The name people see. |
| `notes` | `str \| None` | For an agent: data retention, rate limits, routing, and gotchas. Short, with the same limit as `agent_notes`. |
| `tags` | `list[str]` | Labels, by the tag rules above. |
| `models_dev_id` | `str \| None` | The provider's id in models.dev. `None` when models.dev has no entry for the provider. |

The list has an item for every `ModelProviderName`, including the ones that
models.dev does not have.

Harness Tuner joins a provider entry to models.dev with `models_dev_id` and
the entry's `model_id`. When Kiln does not publish `models_dev_id`, the
tuner uses a built-in table, a port of the Kiln server's
`KILN_TO_MODELS_DEV_PROVIDER` and `PROVIDERS_WITHOUT_MODELS_DEV`
(`kiln_server`, `api/kiln_fastapi_api/tools/model_info/model_builder.py`).
A published `models_dev_id` wins over the built-in table. A `None` value
does not override the table: the tuner then uses its built-in table. So
this list is the place to add or correct a mapping.

The starting values of `models_dev_id`. They come from the Kiln server's
table. Each value was checked against the models.dev file of 2026-11-13.

| `id` | `models_dev_id` | Note |
|---|---|---|
| `openai` | `openai` | |
| `anthropic` | `anthropic` | |
| `gemini_api` | `google` | |
| `vertex` | `google-vertex` | |
| `openrouter` | `openrouter` | |
| `groq` | `groq` | |
| `amazon_bedrock` | `amazon-bedrock` | |
| `azure_openai` | `azure` | |
| `fireworks_ai` | `fireworks-ai` | |
| `together_ai` | `togetherai` | |
| `siliconflow_cn` | `siliconflow-cn` | |
| `cerebras` | `cerebras` | |
| `cloudflare` | `cloudflare-workers-ai` | Not in the Kiln server's table. `claude-maintain-models` already uses this models.dev key. |
| `featherless_ai` | `None` | Not in models.dev. |
| `typesafe` | `None` | Not in models.dev. |
| `huggingface` | `None` | models.dev has a `huggingface` key. The Kiln server leaves it out. Check that it is the same service before you set it. |
| `ollama` | `None` | Local models. |
| `docker_model_runner` | `None` | Local models. |
| `kiln_fine_tune` | `None` | Fine-tunes. |
| `kiln_custom_registry` | `None` | Custom models. |
| `openai_compatible` | `None` | User-defined servers. |

The friendly names exist today in `provider_name_from_id`
(`libs/core/kiln_ai/adapters/provider_tools.py`).

## The maintenance skill

`claude-maintain-models` changes so that:

- it fills `agent_notes` and model `tags` for each new model;
- it fills provider-entry `tags` for each new provider entry;
- it documents every tag and its meaning, and the rule for a new tag;
- it says what goes in `agent_notes` and what does not (the section above);
- it keeps the provider list current. "Adding a Net-New Provider" and its
  touchpoint checklist get an item for the provider list.

## The backfill

- `agent_notes` and tags for the featured models, and for each model
  released in the last 12 months that has a provider entry that is not
  deprecated. On 2026-11-13 that was about 143 models, by the models.dev
  release dates. All 13 featured models are in that set.
- The other models stay empty until a maintainer changes them.
- The provider list in full, with notes for each provider that a person can
  connect.
- A note states only what a maintainer can support from the provider's
  documentation, a public benchmark, or Kiln's own tests.

## Who reads this data

Harness Tuner reads the published file with its own models. It does not
import `kiln_ai`. Its parse is tolerant: it validates each model and each
provider entry alone, drops what is not valid, and ignores fields it does
not know. Until this project ships, the new fields are empty for it, and
its tools work with the other fields.

## Not in this project

- `superseded_by`: a model can infer that a newer model of the same line
  replaces an old one. When it matters, `agent_notes` says so.
- A size class: price is close to a tier.
- Release date and open weights: models.dev has them.
- Zero data retention as a field: the provider's `notes` say it.
- Changes to the web UI, to `/api/available_models`, and to the Kiln
  server's model info tool.

## Questions for the functional spec

- Where does the provider list live in code: a new model and list in
  `ml_model_list.py`, or a new module beside it? Does `KilnRemoteConfig`
  read it, or does only the publish write it?
- Do the friendly names in the provider list replace
  `provider_name_from_id`, or come from it?
- Which tests keep the data correct? For example: each tag follows the
  format and is in the documented set; each `ModelProviderName` has one
  provider-list item; the backward-compatibility test passes with the new
  fields and the new key.
