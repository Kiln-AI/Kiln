---
status: complete
---

# Phase 4: Model info endpoints and the models.dev cache

## Overview

Three read-only endpoints under `/api/model_info/` that join Kiln's model list with the public models.dev catalogue, so agents (through `call_kiln_api`) and other clients can choose models, compare prices and find exact Kiln model ids. The join and the answers are a port of harness-tuner's model info code at commit `b49f159`, without its model policy and its per-run snapshot. models.dev is loaded lazily into an in-memory cache with a 6 h freshness window, single flight, a bounded wait and retry intervals after a failure.

Spec: [model_info](../components/model_info.md) (all sections); architecture sections 6 (step 3) and 9.

## Steps

1. **`kiln_ai/utils/config.py`**: add `"skip_models_dev": ConfigProperty(bool, env_var="KILN_SKIP_MODELS_DEV", default=False, in_memory=True)`.

2. **Root `conftest.py`**: autouse fixture `skip_models_dev(monkeypatch)` that does `monkeypatch.setenv("KILN_SKIP_MODELS_DEV", "true")`.

3. **`kiln_ai/adapters/remote_config.py`**: `@dataclass class RemoteModelListState: loaded_at: datetime | None = None`, one module instance beside `refresh_lock`, a reader `remote_model_list_loaded_at() -> datetime | None`; `refresh_model_list` sets `loaded_at = datetime.now(timezone.utc)` inside its `with refresh_lock:` block.

4. **`provider_api.py`**: move the body of `get_available_models` into a module-level `async def available_models() -> List[AvailableModels]` above `connect_provider_api` (local `available_models` renamed `provider_models`); the route returns `await available_models()`. Open item 13.1: legacy custom models (`<provider>::<model>`) are listed under `provider_id=openai_compatible`, which the run code resolves as an OpenAI-compatible server named `<provider>` and fails; list them under `provider_id=kiln_custom_registry` (provider name from `provider_name_from_id`), which the run code resolves.

5. **`studio_server/services/__init__.py`, `services/model_info/__init__.py`** (empty).

6. **`services/model_info/catalog_schema.py`**: `CatalogEntry`, `CatalogModel`, `CatalogProvider`, `Catalog` (`models`, `providers`, `.model(id)`, `.provider(id)` through cached indexes), ported from HT `model_catalog/schema.py` without `Source`, `fetched_at`, `unavailable`.

7. **`services/model_info/catalog_build.py`**:
   - `KilnModelList` (frozen dataclass: `models`, `providers`, `loaded_at`), the build's input. It lives here, not in `service.py`, because `service.py` imports this module.
   - `Prices`, `ModelsDevData` (frozen: `providers`, `loose_dates`, `canonical_prices`), `parse_models_dev(body: bytes) -> ModelsDevData` (raises `ValueError("not valid JSON")` / `ValueError("not an object")`; keeps only the keys the join reads, then builds the two indexes).
   - `build_catalog(kiln: KilnModelList, models_dev: ModelsDevData | None) -> Catalog`: typed conversion from `KilnModel` / `KilnModelProvider` / `KilnProviderInfo` (first duplicate name wins; `_note`, `_tags`, `KILN_SUGGESTED_FOR`), then HT's join (`_join`, prices, limits, preference order `PREFERENCE`, median, loose date) only when `models_dev` is given. The models.dev provider of an entry is its `KilnProviderInfo.models_dev_id`, nothing else.
   - `kiln_suggested_for(flags: Mapping[str, Any]) -> list[str]` for both Kiln objects (through `model_dump(include=...)`) and server dicts.

8. **`services/model_info/models_dev.py`**: `MODELS_DEV_URL`, `utc_now()`, `default_client()`, `ModelsDevSnapshot`, `ModelsDevSource` (Protocol), `ModelsDevCache` with `enabled`, `current()`, `settle()`, `aclose()` and the state machine and fetch of model_info section 5 (conditional GET with `If-None-Match`, 304 handling, `max_bytes` per chunk, `asyncio.wait_for` bound, parse in `asyncio.to_thread`, the failure reasons, one warning per failure, single flight, other-loop guard, retry intervals).

9. **`api_models/model_info_models.py`**: `ModelInfoStatus`, `ModelInfoKilnSource`, `ModelInfoModelsDevSource`, `ModelInfoSources`, `ModelInfoProviderEntryRow`, `ModelInfoRow`, `ModelInfoList`, `ModelInfoProviderEntryDetails`, `ModelInfoDetails`, `ModelInfoProviderRow`, `ModelInfoProviderList`, with HT's field descriptions.

10. **`services/model_info/view.py`**: `ListModelsQuery`, `ModelNotFoundError`, `InvalidModelQueryError`, `Offered` (`from_payload`), `status`, `_merged` (explicit assignments for the three server fields), entry and row filters, the sorts, `search_rows`, `list_models`, `model_details` (exact then unique case-insensitive lookup; closest ids in the 404 text), `list_providers` (all providers, `connected` / `not_connected`).

11. **`services/model_info/service.py`**: `read_kiln_model_list()` (snapshot of `built_in_models` and the load time under `refresh_lock`, plus `built_in_providers`), `ModelInfoService` with `list_models`, `model_details`, `list_providers`; it gathers the inputs per request, builds `sources` from the injected clock, and reuses the last catalogue while the models.dev data object and the Kiln model objects are the same (`is`).

12. **`studio_server/model_info_api.py`**: `AvailableModelsFn`, `connect_model_info_api(app, *, available_models, models_dev)` with the three routes (`tags=["Providers & Models"]`, `ALLOW_AGENT`, a summary and a docstring each, `Annotated[..., Query(description=...)]` parameters with the validation of section 1.1); maps `ModelNotFoundError` -> 404 and `InvalidModelQueryError` -> 422.

13. **`desktop_server.py`**: after `connect_provider_api(app)`, build `ModelsDevCache(enabled=not Config.shared().skip_models_dev)`, store it on `app.state.models_dev_cache`, call `connect_model_info_api(app, available_models=available_models, models_dev=...)`; in `lifespan`'s `finally`, after `job_registry.events.shutdown()`, `await cache.aclose()` when present.

14. **Test data**: copy HT's `tests/fixtures/model_catalog/models_dev.json` and `kiln_config.json` to `services/model_info/test_data/`.

15. **Generated files**: `make annotations` equivalent (`dump_annotations` on the app's OpenAPI document) for the three new routes, and `generate_schema.sh` for `api_schema.d.ts`.

## Tests

- `services/model_info/test_catalog_build.py` (port of HT `test_model_catalog.py` build cases, Kiln slice loaded through `deserialize_config_data`, providers = the fixture's `provider_list` validated as `KilnProviderInfo` plus the built-in providers it lacks):
  - `test_the_fixture_builds_with_prices_limits_and_dates`
  - `test_price_is_matched_on_the_exact_pair`
  - `test_model_facts_follow_the_provider_preference`
  - `test_the_loose_match_dates_a_model_with_no_exact_match`, `test_the_loose_match_takes_the_earliest_date`, `test_a_loose_date_counts_a_deprecated_entry`, `test_a_short_loose_key_is_not_used`, `test_an_exact_match_with_no_date_falls_back_to_the_loose_date`
  - `test_the_median_price_is_across_every_models_dev_provider`, `test_the_median_needs_three_paid_prices`, `test_a_provider_with_many_entries_counts_once_at_its_lowest_price`, `test_the_canonical_id_and_reasoning_follow_the_provider_preference`
  - `test_kiln_suggested_for_has_the_clear_names`
  - `test_the_models_dev_id_is_used`, `test_a_provider_without_models_dev_id_is_not_joined`
  - `test_a_bad_price_and_a_bad_limit_are_dropped`
  - `test_tags_are_cleaned_deduplicated_and_capped`, `test_a_long_note_is_cut`
  - `test_a_duplicate_model_name_keeps_the_first`
  - `test_a_lookup_does_not_change_equality`
  - `test_no_models_dev_gives_null_prices_and_kiln_data`
  - `test_parse_models_dev_rejects_bad_json_and_a_non_object`, `test_parse_models_dev_keeps_only_the_joined_keys`
- `services/model_info/test_models_dev.py` (fake clock, `httpx.MockTransport`): cases (1)–(9) of model_info section 12, including (8b) and (8c), and the other-loop guard.
- `services/model_info/test_view.py` (port of HT `test_gateway_model_info.py` without policy cases): the three statuses; `Offered` from bad payloads; ready-only default; `include_not_available`; deprecated default; entry filters; null fails a filter; `reasoning_model` apart from thinking levels; tag filter ANY and on an entry; price sort with median and zero price; featured/price/newest with ties; paging and `total`; a pair and a model the catalogue lacks; server values win; details list every entry; provider counts, order, unconnected listed. New: search ranks 0–3, typo pass and `fuzzy_match`, empty search result, search order against an explicit `sort`, search with no letter or digit; `featured` true/false; `include_notes`; unknown provider; case-insensitive details lookup and an ambiguous one; closest ids in the not-found text; the no-entry-for-provider text; no models.dev data.
- `services/model_info/test_service.py`: catalogue rebuilt when the models.dev data object changes and when the Kiln list changes, reused otherwise; `sources` for `remote_config` and `built_in` with ages from the fake clock; `read_kiln_model_list` reads the load time.
- `studio_server/test_model_info_api.py`: query parsing (repeated `tags`, booleans), 422 for `limit` 0 and 201 and 13 tags, the 404 and 422 bodies of section 1.4, `sources` in all three answers, `x-agent-policy` allow and no `x-mcp-policy` on each route.
- Edited: `test_provider_api.py` (`available_models()` equals the route's answer; legacy custom models under `kiln_custom_registry`), `test_remote_config.py` (load time set on success, not on failure), `test_config.py` (`skip_models_dev` in the env-backed bool list, in memory, default false), `test_dev_server.py` (the dev env does not set `KILN_SKIP_MODELS_DEV`), a desktop test that `make_app()` under the suite has `app.state.models_dev_cache.enabled is False`, and that `lifespan` closes the cache.

## Note for phase 12

The route descriptions are incomplete in `app/desktop/studio_server/api_models/model_info_models.py`:
- `ModelInfoProviderEntryRow`, `ModelInfoProviderEntryDetails` and `ModelInfoProviderRow` have no class docstrings.
- `display_name`, `deprecated` and `default_thinking_level` have no `Field` descriptions.
