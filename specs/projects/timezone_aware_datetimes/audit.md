# Timezone-Aware Datetimes: Audit

## 1. Datetime Fields in `libs/core/kiln_ai/datamodel/**/*.py`

| File | Line | Field | Type |
|---|---|---|---|
| `libs/core/kiln_ai/datamodel/basemodel.py` | 310 | `created_at` | `datetime` (default_factory=`datetime.now`) |

`created_at` is the **only** datetime field declared in the datamodel directory. It is inherited by all `KilnBaseModel` subclasses.

## 2. `datetime.now()` / `datetime.utcnow()` Calls Across the Repo

### Production Code

| File | Line | Call | Classification |
|---|---|---|---|
| `libs/core/kiln_ai/datamodel/basemodel.py` | 311 | `default_factory=datetime.now` | **Storage default** -- the field factory for `created_at` on all models. |
| `libs/core/kiln_ai/utils/logging.py` | 48 | `start_time=datetime.datetime.now()` | **Unrelated** -- passed to litellm `Logging` constructor for curl logging; never compared to stored timestamps. |
| `app/desktop/studio_server/provider_api.py` | 2050 | `datetime.now() - self.last_updated` | **"now" math** -- cache staleness check; compares naive `now()` against naive `last_updated`. |
| `app/desktop/studio_server/provider_api.py` | 2157 | `last_updated=datetime.now()` | **Storage default** -- sets cache timestamp. Paired with line 2050 comparison. |

No calls to `datetime.utcnow()` found anywhere in the repo.

### Test Code

| File | Line | Call | Classification |
|---|---|---|---|
| `libs/core/kiln_ai/datamodel/test_basemodel.py` | 109 | `now = datetime.datetime.now()` | **Test fixture** -- used to assert `created_at` is close to now. |
| `libs/core/kiln_ai/datamodel/test_eval_model.py` | 1900 | `config1.created_at = datetime.now()` | **Test fixture** -- assigns naive datetime to model field. |
| `libs/core/kiln_ai/datamodel/test_eval_model.py` | 1911 | `config2.created_at = datetime.now() + timedelta(seconds=1)` | **Test fixture** -- assigns naive datetime to model field. |
| `app/desktop/studio_server/test_tool_api.py` | 2721 | `mock_tool_server.created_at = datetime.now()` | **Test fixture** -- assigns naive datetime to model field. |
| `app/desktop/studio_server/test_tool_api.py` | 2797 | `mock_tool_server.created_at = datetime.now()` | **Test fixture** -- assigns naive datetime to model field. |
| `app/desktop/studio_server/test_tool_api.py` | 2868 | `mock_tool_server.created_at = datetime.now()` | **Test fixture** -- assigns naive datetime to model field. |
| `app/desktop/studio_server/test_tool_api.py` | 2950 | `mock_tool_server.created_at = datetime.now()` | **Test fixture** -- assigns naive datetime to model field. |
| `app/desktop/studio_server/test_provider_api.py` | 1958 | `cache.last_updated = datetime.now()` | **Test fixture** -- assigns naive datetime to cache field. |
| `app/desktop/studio_server/test_provider_api.py` | 1965 | `cache.last_updated = datetime.now() - timedelta(minutes=61)` | **Test fixture** -- assigns naive datetime to cache field. |
| `app/desktop/studio_server/test_provider_api.py` | 1969 | `cache.last_updated = datetime.now()` | **Test fixture** -- assigns naive datetime to cache field. |
| `app/desktop/studio_server/test_provider_api.py` | 2020 | `last_updated=datetime.now()` | **Test fixture** -- assigns naive datetime to cache field. |
| `libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_streaming.py` | 79 | `datetime.now(timezone.utc)` | **Unrelated / test fixture** -- generates a timestamp string for test file naming; never compared to stored timestamps. Already aware. |

## 3. `.replace(tzinfo=...)` and `.astimezone(...)` Calls

**None found** anywhere in the repo.

## 4. Comparisons / Arithmetic Against Stored Datetimes

| File | Line | Expression | Notes |
|---|---|---|---|
| `libs/core/kiln_ai/datamodel/basemodel.py` | 310-311 | `created_at` default factory | Origin of all stored datetime values. |
| `libs/core/kiln_ai/datamodel/eval.py` | 432 | `sorted(configs_list, key=lambda c: c.created_at)` | Sorts configs by `created_at`. Safe if all are same awareness. |
| `libs/core/kiln_ai/datamodel/test_basemodel.py` | 110 | `(model.created_at - now).total_seconds()` | Arithmetic: subtracts naive `now` from `created_at`. Will TypeError after Phase 2 if `now` stays naive. |
| `libs/server/kiln_server/document_api.py` | 2538 | `sorted(extractions, key=lambda e: e.created_at, reverse=True)` | Sorts by `created_at`. Safe if all are same awareness. |
| `libs/core/kiln_ai/adapters/rag/deduplication.py` | 15, 26, 35 | `min(group, key=lambda x: x.created_at)` | Compares `created_at` values within groups. Safe if all are same awareness. |
| `app/desktop/studio_server/provider_api.py` | 2038 | `last_updated: datetime \| None = None` | Field declaration on `OpenAICompatibleProviderCache` dataclass. Not a Pydantic model field (plain `@dataclass`), but the value used in the comparisons below. |
| `app/desktop/studio_server/provider_api.py` | 2050 | `datetime.now() - self.last_updated > timedelta(minutes=60)` | Arithmetic comparing naive `now()` to naive `last_updated`. Not a model field but same pattern -- both sides must match awareness. |

## 5. Tests That Construct Naive Datetimes for Use Against Models

### Direct `datetime(...)` constructor (naive, no tzinfo)

| File | Line(s) | Description |
|---|---|---|
| `libs/core/kiln_ai/adapters/rag/test_rag_runners.py` | 777, 783, 791, 817, 825, 833, 866, 874, 945, 950, 956, 984, 987, 996, 999, 1008, 1011, 1039, 1042, 1051, 1054, 1119, 1123, 1127, 1137, 1141, 1145, 1155, 1159, 1163, 1196, 1200, 1204, 1214, 1218, 1222, 1259, 1263, 1268, 1286, 1290, 1335, 1339, 1389, 1393, 1462, 1466, 1534, 1538, 1599, 1603, 1677, 1681 | Assigns `datetime(2023, 1, N)` to `created_at` on mock extraction/chunked_doc/chunk_embeddings objects. |
| `libs/core/kiln_ai/adapters/rag/test_deduplication.py` | 153, 157, 169, 173, 185, 189 | Assigns naive date strings `"2024-01-01"` / `"2024-01-02"` to `created_at`. |
| `libs/core/kiln_ai/adapters/rag/test_rag_runners.py` | 2188, 2197, 2206, 2247, 2252, 2263, 2268, 2309, 2313, 2318, 2329, 2333, 2338 | Assigns naive date strings `"2024-01-01"` etc. to `created_at`. |
| `libs/core/kiln_ai/adapters/rag/test_progress.py` | 51, 63, 77 | Assigns `"2024-01-01T00:00:00Z"` to `created_at`. (Note: these are **aware** -- `Z` suffix.) |

### `datetime.now()` assigned to model fields

| File | Line(s) | Description |
|---|---|---|
| `libs/core/kiln_ai/datamodel/test_basemodel.py` | 109 | `now = datetime.datetime.now()` used for comparison against `created_at`. |
| `libs/core/kiln_ai/datamodel/test_eval_model.py` | 1900, 1911 | `config.created_at = datetime.now()` -- direct naive assignment to model field. |
| `app/desktop/studio_server/test_tool_api.py` | 2721, 2797, 2868, 2950 | `mock_tool_server.created_at = datetime.now()` -- direct naive assignment to model field. |

### Naive datetime strings in test JSON fixtures

| File | Line | String |
|---|---|---|
| `libs/core/kiln_ai/datamodel/test_extraction_model.py` | 519 | `"2025-10-15T01:16:38.380098"` |
| `libs/core/kiln_ai/datamodel/test_vector_store.py` | 389, 435, 484, 528 | `"2025-10-15T01:16:38.380098"` |
| `libs/core/kiln_ai/datamodel/test_chunk_models.py` | 659, 733 | `"2025-10-29T13:19:53.872744"` |
| `libs/core/kiln_ai/datamodel/test_chunk_models.py` | 686, 774 | `"2025-10-15T18:29:28.023477"` |
| `libs/core/kiln_ai/datamodel/test_task.py` | 261 | `"2025-06-09T13:33:35.276927"` |

These are legacy-format naive ISO strings. After Phase 2, the validator will promote them to aware-local on load, so they will continue to work correctly.

## Summary

**What needs to change (Phases 2-4):**

1. **`basemodel.py:311`** -- `default_factory=datetime.now` must become `lambda: datetime.now().astimezone()`. Add field validator for naive-to-aware promotion.
2. **`provider_api.py:2050,2157`** -- Cache `datetime.now()` calls and comparison must be awareness-consistent. Both sides currently naive; either both stay naive (no serialization) or both become aware. The cache is never serialized to disk so keeping both naive is safe, but switching to aware is also fine.
3. **`test_basemodel.py:109`** -- `datetime.datetime.now()` must become `datetime.datetime.now().astimezone()` to match the now-aware `created_at`.
4. **`test_eval_model.py:1900,1911`** -- naive `datetime.now()` assignments will be auto-promoted by the validator (via `validate_assignment=True`), so they may not need changes. But explicit aware datetimes are cleaner.
5. **`test_tool_api.py:2721,2797,2868,2950`** -- same as above: naive assignments will be auto-promoted. May need explicit aware datetimes if tests assert on timezone properties.
6. **`test_provider_api.py:1958,1965,1969,2020`** -- cache field is a plain dataclass, not Pydantic, so no auto-promotion. Must match awareness of `datetime.now()` in `is_stale()`.
7. **`test_rag_runners.py`** (53 lines) -- naive `datetime(2023, 1, N)` assignments to mock objects. These are mock objects (not real Pydantic models), so `validate_assignment` won't fire. They will need updating only if compared against aware datetimes.
8. **`logging.py:48`** -- `datetime.datetime.now()` is unrelated (passed to litellm, never compared to stored timestamps). **No change needed.**
9. **Sorting call sites** (`eval.py:432`, `document_api.py:2538`, `deduplication.py:15,26,35`) -- safe as long as all `created_at` values in a collection have consistent awareness. After Phase 2, all loaded values will be aware, so these are fine.
10. **Frontend `formatDate`** -- needs test coverage for all three ISO formats. No production code change needed.
