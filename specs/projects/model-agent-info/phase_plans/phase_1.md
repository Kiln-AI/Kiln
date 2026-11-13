---
status: complete
---

# Phase 1: Code and tests

## Overview

Add the code side of the project with the new data empty: the vocabulary
module (tag maps, tag format, limits), the provider list with friendly names
and `models_dev_id` values, the new `agent_notes` and `tags` fields on
`KilnModel` and `tags` on `KilnModelProvider`, `provider_name_from_id`
reading the provider list, and `serialize_config` writing `provider_list`.
Tests guard the data rules, the published shape, and tolerant loading. No
skill or guidance edits (Phase 2) and no backfill (Phase 3).

## Steps

1. New `libs/core/kiln_ai/adapters/model_agent_info.py`:
   - Module docstring: these notes and tags are for agents that choose or
     configure a model; the rules are enforced by tests on the built-in
     data, never at parse time, so an older client keeps loading a newer
     file.
   - `TAG_PATTERN: Final = re.compile(r"^[a-z0-9_]{1,40}$")`,
     `MAX_TAGS_PER_ENTRY: Final = 12`, `MAX_NOTE_CHARS: Final = 2000`.
   - `MODEL_TAGS`, `PROVIDER_ENTRY_TAGS`, `PROVIDER_LIST_TAGS` as
     `Final[Mapping[str, str]]` dict literals with the overview's meanings
     word for word; a one-line comment above each says where its tags go.
     `PROVIDER_LIST_TAGS` is empty.

2. New `libs/core/kiln_ai/adapters/ml_provider_list.py`:
   - `KilnProviderInfo(BaseModel)` with `id: ModelProviderName`,
     `friendly_name: str`, `notes: str | None = None`,
     `tags: list[str] = Field(default_factory=list)`,
     `models_dev_id: str | None = None`, and an Attributes docstring.
   - `built_in_providers: tuple[KilnProviderInfo, ...]`, one item per
     `ModelProviderName` in enum order, friendly names copied from the
     current `match` in `provider_name_from_id`, `models_dev_id` from the
     overview's table.
   - `get_provider_info(provider: ModelProviderName) -> KilnProviderInfo`:
     linear scan, raises `ValueError` when missing.

3. `libs/core/kiln_ai/adapters/ml_model_list.py`:
   - Import `Field` from pydantic.
   - `KilnModel`: `agent_notes: str | None = None` and
     `tags: list[str] = Field(default_factory=list)` under `# Editorial`;
     Attributes lines for `editorial_notes`, `agent_notes` and `tags`.
   - `KilnModelProvider`: `tags: list[str] = Field(default_factory=list)`
     after `deprecated`; an Attributes line.

4. `libs/core/kiln_ai/adapters/provider_tools.py`: replace the `match` in
   `provider_name_from_id` with
   `get_provider_info(ModelProviderName(id)).friendly_name`; keep the
   unknown-id result; update the Raises line.

5. `libs/core/kiln_ai/adapters/remote_config.py`: add a required
   `providers: Sequence[KilnProviderInfo]` argument before `path` in
   `serialize_config`; write `"provider_list"` with a short comment that it
   is for agents outside Kiln and `deserialize_config_data` does not load
   it. `dump_builtin_config` passes `built_in_providers`.

## Tests

`test_model_agent_info.py` (new):
- `assert_valid_tags(tags, allowed)` helper: format, membership, no
  duplicates, count; names the bad tag.
- Each map key matches `TAG_PATTERN`; each meaning is non-blank.
- No tag in both the model map and the provider-entry map.
- The starting tag sets are exactly the overview's.
- The helper rejects a bad format, an unknown tag, a duplicate, and too
  many tags, and accepts a valid list.

`test_ml_provider_list.py` (new):
- Provider ids equal `list(ModelProviderName)`.
- Per provider (parametrized): friendly name non-blank; `models_dev_id`
  `None` or matches `^[a-z0-9-]+$`; tags valid against
  `PROVIDER_LIST_TAGS`; notes by the note rule.
- `get_provider_info` returns the item for each provider, and raises
  `ValueError` for a provider missing from the list (patched list).
- The `models_dev_id` values match the overview's table.

`test_ml_model_list.py`:
- Per built-in model (parametrized by name): model tags valid against
  `MODEL_TAGS`; each provider entry's tags valid against
  `PROVIDER_ENTRY_TAGS`; `agent_notes` by the note rule.

`test_provider_tools.py`:
- Parametrized over every `ModelProviderName`: `provider_name_from_id`
  returns the list's friendly name, non-blank, not "Unknown provider".

`test_remote_config.py`:
- Update the two `serialize_config` calls.
- Serialized file: `provider_list` has one item per provider with exactly
  the five keys and enum ids; each model has `agent_notes` and `tags`;
  each provider entry has `tags`.
- `deserialize_config_data` loads a payload with `provider_list` (a valid
  list and a malformed string) and loads the models.
- An unknown model tag, a 3,000-character `agent_notes` and an unknown
  provider-entry tag load unchanged.
- A payload without the new fields loads with the defaults.
- Run `test_backwards_compatibility_with_v0_19` with
  `KILN_TEST_COMPATIBILITY=1`.
