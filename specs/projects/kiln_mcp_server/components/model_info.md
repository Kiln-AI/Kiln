---
status: draft
---

# Component: Model info endpoints

Three read-only REST endpoints that join Kiln's model list with the public models.dev catalogue (functional spec section 8). They are a port of harness-tuner's model info code (HT below; paths under `harness-tuner/src/kiln_harness_tuner/`), without HT's model policy and without its per-run snapshot. Agents reach them through `call_kiln_api`. The web UI and other clients may use them too.

Out of scope: a reload of Kiln's own model list (it still loads once at app start), a disk cache, and the web UI's own models.dev fetch.

## 1. Endpoints

All three routes: `tags=["Providers & Models"]`, `openapi_extra=ALLOW_AGENT`, no `x-mcp-policy` tag, a `summary`, and a docstring written for API readers. Every answer has a `sources` block (section 2.1). Parameters use `Annotated[..., Query(description=...)]`, as `libs/server/kiln_server/memory_api.py` does. A list parameter repeats the key.

### 1.1 `GET /api/model_info/models`

| Parameter | Type | Default | Validation | Meaning |
|---|---|---|---|---|
| `search` | str | none | 1-100 chars | Name search on the model id and display name (section 7). |
| `featured` | bool | none | | `true`: only models with a `kiln_featured_rank`. `false`: only models without one. |
| `provider` | str | none | 1-200 chars | Kiln provider id. Keeps only that provider's entries. |
| `family` | str | none | 1-100 chars | Exact match on `family`. |
| `tags` | list[str] | none | at most 12 values, each 1-40 chars | A row passes when it has ANY of these tags, on the model or on a kept provider entry. |
| `supports_tools`, `supports_vision`, `has_thinking_levels` | bool | none | | Entry filters. |
| `reasoning_model`, `open_weights` | bool | none | | Row filters (models.dev facts). |
| `include_not_available` | bool | `false` | | Also list entries whose status is not `ready`. |
| `include_deprecated` | bool | `false` | | Also list deprecated entries. |
| `include_notes` | bool | `false` | | Fill `editorial_notes` and `agent_notes` in each row. |
| `sort` | `featured`, `price` or `newest` | none | | See step 5. |
| `limit` | int | `25` | 1-200 | Page size. |
| `offset` | int | `0` | >= 0 | Rows to skip. |

Steps, in this order:

1. Build the merged rows (section 6.3).
2. Entry filters. An entry is kept when: its status is `ready`, or `include_not_available` is true; it is not deprecated, or `include_deprecated` is true; `provider` is not given or equals the entry's provider; each given entry filter equals the entry's value (`has_thinking_levels` compares with `bool(entry.thinking_levels)`). A null value fails a filter that tests it, for `true` and for `false`.
3. Row filters. A row is kept when: at least one entry is left; `family` matches; `open_weights` and `reasoning_model` equal the given values (null fails); `featured` matches; `tags` matches (ANY).
4. Search (section 7), on the rows left after step 3.
5. Sort. The base order is Kiln's list order, then the models that only `/api/available_models` knows, by id. A stable sort by featured rank is always applied first (ranked rows by rank, then the rest in base order). Then:
   - `sort=price`: ascending by `median_input_price + median_output_price`; when either is null, by the cheapest kept entry that has both prices above 0; rows with no price go last. A price of 0 never sorts.
   - `sort=newest`: `release_date` descending; rows with no date go last.
   - `sort=featured`: nothing more.
   - no `sort` and no `search`: the same as `featured`. No `sort` with `search`: best match first, ties in featured order. An explicit `sort` with `search` uses that sort and ignores the match rank.
6. Page: `rows[offset : offset + limit]`. `total` is the row count after step 4, the same on every page. An `offset` past the end gives an empty `models` list.
7. A row lists only its kept entries. `has_thinking_levels` is computed over the kept entries.

### 1.2 `GET /api/model_info/model_details`

| Parameter | Type | Default | Validation | Meaning |
|---|---|---|---|---|
| `model_id` | str | required | 1-200 chars | A Kiln model id. |
| `provider` | str | none | 1-200 chars | Keep only this provider's entry. |

The id is a query parameter because ids of custom, fine-tuned and local models hold `::`, `:` and `/`, and a path segment cannot carry `/`.

Lookup over the merged rows, with no status or deprecation filter:

1. A row whose `model` equals `model_id`.
2. Else the rows whose `model.casefold()` equals `model_id.casefold()`. One row: use it. The answer's `model` field has the correct spelling.
3. Else, or with more than one row in step 2: 404.
4. With `provider`: keep the entries whose provider equals it exactly. None left: 404.

### 1.3 `GET /api/model_info/providers`

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `include_not_available` | bool | `false` | Also list providers that are not connected. |

Provider ids: the built-in provider list, then providers seen in model entries, then connected providers, without duplicates. Unconnected providers are left out by default. Order: `ready_model_count` descending, then id.

### 1.4 Errors

Kiln's error handler turns `HTTPException.detail` into `{"message": ...}`. FastAPI validation errors (a missing `model_id`, `limit=0`, 13 tags, a bad boolean) are 422 in Kiln's usual shape.

| Case | Status | `message` |
|---|---|---|
| Unknown model, some close ids | 404 | `Model not found: <id>. Closest ids: <a>, <b>, <c>. To find a model id, call GET /api/model_info/models with search=<name> and include_not_available=true.` |
| Unknown model, no close id | 404 | The same text without the `Closest ids` sentence. |
| Model has no entry for `provider` | 404 | `Model <model> has no entry for provider <provider>. Its providers: <a>, <b>.` |
| `provider` (list route) is not a known provider id | 422 | `Unknown provider: <provider>. Provider ids: <sorted ids>.` |
| `search` holds no letter and no digit | 422 | `search needs at least one letter or digit.` |

Closest ids: the first three ids that the search of section 7 gives for `model_id` over all merged rows (rank pass, then the typo pass). Known provider ids are the ids of section 1.3. The 422 on an unknown provider is there because a wrong id (`google` for `gemini_api`) would otherwise give an empty list that reads as "no such models".

## 2. Response models

File `app/desktop/studio_server/api_models/model_info_models.py`. Plain `BaseModel` classes, list fields with `Field(default_factory=list)`. Every class name starts with `ModelInfo`, because `provider_api.py` already defines `ModelDetails`, `AvailableModels` and `ProviderModels` and the names are global in the OpenAPI schema. Keep HT's field descriptions (`gateway/models.py:123-136`): they reach the agent through the generated API reference. All prices are USD per million tokens; null means "no price data", not "free".

### 2.1 `ModelInfoSources`

| Field | Type | Meaning |
|---|---|---|
| `kiln_model_list` | `ModelInfoKilnSource` | Where Kiln's model list came from. |
| `models_dev` | `ModelInfoModelsDevSource` | The state of the models.dev data. |

| Class | Field | Type | Meaning |
|---|---|---|---|
| `ModelInfoKilnSource` | `origin` | `"remote_config"` or `"built_in"` | `remote_config`: the remote list was loaded in this process. `built_in`: the list shipped with the installed app (offline at start, skipped, or failed). |
| | `loaded_at` | datetime or null | UTC time of the last good remote load. Null for `built_in`. |
| | `age_seconds` | int or null | Now minus `loaded_at`. |
| `ModelInfoModelsDevSource` | `state` | `"ok"`, `"stale"` or `"unavailable"` | `ok`: data younger than 6 h. `stale`: older data is served. `unavailable`: no data; every models.dev field is null. |
| | `loaded_at` | datetime or null | UTC time the data was fetched, or last confirmed unchanged by a 304. |
| | `age_seconds` | int or null | Now minus `loaded_at`. |
| | `detail` | str or null | Null when `ok`. Else one of: `turned off`, `loading`, `not loaded`, `refresh running`, or the last failure reason (section 5.3). |

### 2.2 List models

`ModelInfoList`: `sources: ModelInfoSources`; `total: int` (rows after all filters); `fuzzy_match: bool` (true: no model held the search words, and the rows are the closest names); `models: list[ModelInfoRow]`.

| `ModelInfoRow` field | Type | Meaning |
|---|---|---|
| `model` | str | Kiln's model id (`KilnModel.name`). Use it in a run config. |
| `display_name` | str | `friendly_name`; for a model only `/api/available_models` knows, its `name`. |
| `family` | str or null | Kiln's model family. |
| `kiln_featured_rank` | int or null | Kiln's ranking, 1 first. |
| `tags` | list[str] | Kiln's model tags (`current`, `recommended`, `top_value`, ...). |
| `release_date` | str or null | ISO date, from models.dev. |
| `context_window` | int or null | Tokens, from the preferred models.dev entry. |
| `open_weights` | bool or null | From models.dev. |
| `reasoning_model` | bool or null | The model reasons before it answers, also when that is always on (models.dev). |
| `has_thinking_levels` | bool | At least one listed entry has thinking levels that a run config can set. |
| `median_input_price`, `median_output_price` | float or null | The median price across the providers on models.dev. |
| `editorial_notes`, `agent_notes` | str or null | Kiln's notes. Null unless `include_notes` is true. |
| `providers` | list[`ModelInfoProviderEntryRow`] | The kept entries. |

`ModelInfoProviderEntryRow`: `provider: str` (Kiln provider id), `status: ModelInfoStatus`, `input_price` and `output_price` (float or null), `tags: list[str]`, `deprecated: bool`.

### 2.3 Model details

`ModelInfoDetails` has `sources`, every `ModelInfoRow` field (notes always filled; `has_thinking_levels` over the listed entries), and:

| Extra field | Type | Meaning |
|---|---|---|
| `release_date_estimated` | bool | True: the date came from a match on the model's name only. |
| `knowledge_cutoff` | str or null | From models.dev, as written there. |
| `max_output_tokens` | int or null | From the preferred models.dev entry. |
| `providers` | list[`ModelInfoProviderEntryDetails`] | Every entry of the model, also deprecated and not available ones. |

| `ModelInfoProviderEntryDetails` field | Type | Meaning |
|---|---|---|
| `provider`, `status`, `input_price`, `output_price`, `tags`, `deprecated` | as in the row | |
| `provider_model_id` | str or null | The provider's own id for the model. Null for an entry that came from `/api/available_models`. |
| `untested` | bool | Kiln has not tested this model, usually one a user added. The `supports_*` fields do not apply. |
| `cache_read_price`, `cache_write_price` | float or null | From models.dev. |
| `context_window`, `max_output_tokens` | int or null | This provider's limits, from models.dev. |
| `supports_tools`, `supports_structured_output`, `supports_vision` | bool or null | Kiln's flags for the pair. |
| `supports_temperature` | bool or null | From models.dev. |
| `thinking_levels` | list[str] | The values a run config can set, in Kiln's order. |
| `default_thinking_level` | str or null | |
| `default_structured_output_mode` | str or null | Kiln's suggested default output mode for the pair. |
| `kiln_suggested_for` | list[str] | Any of `eval_judge`, `synthetic_data`, `document_extraction`, `synthetic_user`. |

### 2.4 List providers

`ModelInfoProviderList`: `sources`, `providers: list[ModelInfoProviderRow]`.

| `ModelInfoProviderRow` field | Type | Meaning |
|---|---|---|
| `provider` | str | Kiln provider id. |
| `name` | str or null | Friendly name from `built_in_providers`. |
| `status` | `"connected"` or `"not_connected"` | Connected: the provider is in the `/api/available_models` answer. |
| `ready_model_count` | int | Pairs on this provider with status `ready`. It counts deprecated and untested pairs too; the description says so. |
| `tags` | list[str] | Kiln's provider tags. |
| `notes` | str or null | Kiln's provider notes (data retention, rate limits). |

### 2.5 Status

`ModelInfoStatus = Literal["ready", "not_offered", "not_connected"]`, computed at every request from one in-process call of the `/api/available_models` logic (section 4):

| Value | Rule |
|---|---|
| `ready` | The (provider, model) pair is in the answer: the user can run it now. |
| `not_offered` | The provider is in the answer and the pair is not. Examples: an Ollama model that is not installed; a built-in entry with no `model_id`. |
| `not_connected` | The provider is not in the answer. |

A key provider is in the answer when all its config keys are set, also with zero models. Ollama and Docker Model Runner are in it only when they answer and have at least one model installed.

## 3. Module layout

All under `app/desktop/studio_server/` (the status needs desktop code, and `libs/server` must not know desktop features). `services/` is new: add `services/__init__.py` and `services/model_info/__init__.py`.

| File | Source in HT | Port or rewrite |
|---|---|---|
| `model_info_api.py` | `gateway/ops.py:481-499` | Rewrite. Three thin routes. No `from __future__ import annotations` here. |
| `api_models/model_info_models.py` | `gateway/models.py:120-262` | Port. Drop `blocked_by_policy`; `sources` replaces `catalog`; add the notes on the row and `fuzzy_match`. The request models (`ListModelsArgs`...) become query parameters plus a dataclass. |
| `services/model_info/catalog_schema.py` | `model_catalog/schema.py` | Port nearly unchanged: `CatalogEntry`, `CatalogModel`, `CatalogProvider`, `Catalog` (only `models`, `providers`, `.model()`, `.provider()`). Drop `Source`, `fetched_at`, `Catalog.unavailable`. |
| `services/model_info/catalog_build.py` | `model_catalog/build.py` | Lines 237-445 (join, median, loose date) port unchanged. Lines 58-234 (the tolerant parse of the published JSON) are replaced by a typed conversion from Kiln's objects. `_note`, `_tags`, `KILN_SUGGESTED_FOR`, `PREFERENCE` are kept. |
| `services/model_info/models_dev.py` | `model_catalog/fetch.py` (reason strings only) | Rewrite: `ModelsDevCache` (section 5). |
| `services/model_info/view.py` | `gateway/model_info.py` | Port: `Offered`, `status` (no policy argument), `_merged`, the filters, the sorts, `list_models`, `model_details`, `list_providers`. New: search, `featured`, `include_notes`, the forgiving lookup, the two domain errors. |
| `services/model_info/service.py` | none | New: `ModelInfoService`, which gathers the inputs for each request. |

Dropped from HT: `store.py`, `providers.py` except `PREFERENCE`, `model_policy.py`, `--no-model-catalog`. Edited Kiln files: `provider_api.py` (section 4), `desktop_server.py` (section 8), `libs/core/kiln_ai/adapters/remote_config.py` (section 6.1), `libs/core/kiln_ai/utils/config.py` and the root `conftest.py` (section 8).

Signatures:

```
# model_info_api.py
AvailableModelsFn = Callable[[], Awaitable[Sequence[BaseModel]]]
def connect_model_info_api(app: FastAPI, *, available_models: AvailableModelsFn,
                           models_dev: ModelsDevSource) -> None
    # builds one ModelInfoService; maps ModelNotFoundError -> 404, InvalidModelQueryError -> 422

# services/model_info/service.py
@dataclass(frozen=True)
class KilnModelList:
    models: tuple[KilnModel, ...]
    providers: tuple[KilnProviderInfo, ...]
    loaded_at: datetime | None            # None: the built-in list
def read_kiln_model_list() -> KilnModelList   # one copy of built_in_models under remote_config.refresh_lock

class ModelInfoService:
    def __init__(self, *, available_models: AvailableModelsFn, models_dev: ModelsDevSource,
                 kiln_model_list: Callable[[], KilnModelList] = read_kiln_model_list,
                 now: Callable[[], datetime] = utc_now) -> None
    async def list_models(self, query: ListModelsQuery) -> ModelInfoList
    async def model_details(self, model_id: str, provider: str | None) -> ModelInfoDetails
    async def list_providers(self, include_not_available: bool) -> ModelInfoProviderList

# services/model_info/view.py   (pure functions)
@dataclass(frozen=True)
class ListModelsQuery: ...               # one field per parameter of 1.1, same names and defaults
class ModelNotFoundError(Exception): ...        # str(error) is the message of 1.4
class InvalidModelQueryError(Exception): ...
class Offered:                                   # as HT
    @classmethod
    def from_payload(cls, payload: Any) -> "Offered"
def status(offered: Offered, provider: str, model: str) -> ModelInfoStatus
def list_models(catalog: Catalog, offered: Offered, sources: ModelInfoSources, query: ListModelsQuery) -> ModelInfoList
def model_details(catalog: Catalog, offered: Offered, sources: ModelInfoSources, model_id: str, provider: str | None) -> ModelInfoDetails
def list_providers(catalog: Catalog, offered: Offered, sources: ModelInfoSources, include_not_available: bool) -> ModelInfoProviderList
def search_rows(query: str, rows: Sequence[CatalogModel]) -> tuple[list[CatalogModel], bool]   # (rows best first, fuzzy)

# services/model_info/catalog_build.py   (pure functions)
@dataclass(frozen=True)
class ModelsDevData:
    providers: Mapping[str, Any]          # models.dev's shape, with only the keys the join reads
    loose_dates: Mapping[str, str]        # loose key -> earliest release date
    canonical_prices: Mapping[str, Prices]
def parse_models_dev(body: bytes) -> ModelsDevData      # ValueError("not valid JSON") or ValueError("not an object")
def build_catalog(kiln: KilnModelList, models_dev: ModelsDevData | None) -> Catalog
```

Each service method does: `kiln = self._kiln_model_list()`; `snapshot = await self._models_dev.current()`; `offered = Offered.from_payload([p.model_dump(mode="json") for p in await self._available_models()])`; `catalog = self._catalog(kiln, snapshot.data)`; build `sources`; call the view function. `_catalog` keeps the last built catalogue and reuses it while `snapshot.data` is the same object and `kiln.models` holds the same objects in the same order (compare with `is`; the kept tuple keeps the objects alive, so an id cannot be reused). The view functions never change the catalogue: `_merged` works on deep copies, as in HT.

## 4. The `/api/available_models` refactor

The logic is a closure inside `connect_provider_api` today (`provider_api.py:282-407`), so nothing else can call it. The exact change:

1. Add a module-level `async def available_models() -> List[AvailableModels]` directly above `connect_provider_api`. Its body is the body of `get_available_models`, unchanged, except that the local variable `available_models` (in the built-in model loop) is renamed to `provider_models`, because it would shadow the function's own name. The body uses module-level names only, so nothing else changes.
2. The route handler becomes `return await available_models()`.
3. `model_info_api.py` does not import `provider_api.py` ("routers are not libraries"). `desktop_server.make_app`, which already imports every router, passes the function in (section 8).

Existing tests patch module-level helpers of `provider_api` (`available_ollama_models`, `Config`, ...) and keep working. The handler reads the payload as plain dicts through `Offered.from_payload`, so HT's tolerant reader and its tests port unchanged, and `view.py` needs no type from `provider_api.py`.

## 5. The models.dev cache

### 5.1 Class

```
MODELS_DEV_URL = "https://models.dev/api.json"

@dataclass(frozen=True)
class ModelsDevSnapshot:
    data: ModelsDevData | None
    state: Literal["ok", "stale", "unavailable"]
    loaded_at: datetime | None
    detail: str | None

class ModelsDevSource(Protocol):
    async def current(self) -> ModelsDevSnapshot: ...

class ModelsDevCache:                     # implements ModelsDevSource
    def __init__(self, *, enabled: bool, url: str = MODELS_DEV_URL,
                 max_age: timedelta = timedelta(hours=6),
                 retry_after: timedelta = timedelta(minutes=10),
                 retry_after_empty: timedelta = timedelta(minutes=1),
                 wait_secs: float = 4.0, fetch_timeout_secs: float = 30.0,
                 max_bytes: int = 50 * 1024 * 1024,
                 now: Callable[[], datetime] = utc_now,
                 client_factory: Callable[[], httpx.AsyncClient] = default_client) -> None
    @property
    def enabled(self) -> bool
    async def current(self) -> ModelsDevSnapshot      # never raises
    async def aclose(self) -> None                    # cancels a refresh in flight; later calls start none
```

The constructor does no I/O and creates no asyncio object. Fields: `_data`, `_etag`, `_loaded_at`, `_last_failure`, `_last_failure_at`, `_task: asyncio.Task | None`, `_closed`. `default_client()` returns `httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=True)`; one short-lived client per refresh. Memory only: no disk cache.

### 5.2 State machine

The state is derived from the fields; it is not stored.

| State | Condition | Answer `state` / `detail` |
|---|---|---|
| off | `enabled` is false | `unavailable` / `turned off` |
| empty | no data, no task | `unavailable` / the last failure reason, or `not loaded` |
| loading | no data, a task runs | `unavailable` / `loading` |
| fresh | data, age < `max_age` | `ok` / null |
| stale | data, age >= `max_age`, no task | `stale` / the last failure reason, or null |
| refreshing | data, age >= `max_age`, a task runs | `stale` / `refresh running` |

| From | Event | To |
|---|---|---|
| empty | `current()`, and no failure in the last `retry_after_empty` | loading |
| loading | 200 with a valid body | fresh |
| loading | any failure | empty (reason and time recorded) |
| fresh | 6 h pass | stale |
| stale | `current()`, and no failure in the last `retry_after` | refreshing |
| refreshing | 200 with a valid body | fresh (new data, new ETag) |
| refreshing | 304 | fresh (same data, `loaded_at` = now) |
| refreshing | any failure | stale (last good data kept, reason and time recorded) |
| any | `aclose()` | the task is cancelled; no new task starts |

### 5.3 `current()` and the refresh

```
current():
  if not enabled: return the "off" snapshot
  now = self._now()
  if (no data or now - loaded_at >= max_age) and not closed:
      task = self._task, or None when it is done or belongs to another event loop
      if task is None and (no failure, or now - last_failure_at >= the retry interval):
          task = self._task = asyncio.create_task(self._refresh())
      if task is not None:
          await asyncio.wait({task}, timeout=wait_secs)      # a timeout does not cancel the task
  return the snapshot for the fields as they are now

_refresh():   # never raises, except CancelledError
  result = await asyncio.wait_for(self._fetch(), fetch_timeout_secs)
  _fetch: GET url, with "If-None-Match: <etag>" only when data and an ETag are held; stream the body
      304 while data is held          -> loaded_at = now; clear the failure
      status other than 200           -> failure "HTTP <code>"
      decoded bytes over max_bytes    -> failure "body over 50 MiB" (counted per chunk; stop reading)
      else data = await asyncio.to_thread(parse_models_dev, body)
           -> data, etag (the response's ETag header), loaded_at = now; clear the failure
  asyncio.TimeoutError or httpx.TimeoutException -> failure "timeout after 30 s"
  other httpx.HTTPError                          -> failure "transport error: <ExcName>"
  ValueError from the parse                      -> failure "not valid JSON" or "not an object"
  any other Exception                            -> failure "fetch failed: <ExcName>"
  a failure: keep data and etag; set last_failure and last_failure_at; log one warning
```

Rules that follow from this:

- **Lazy.** The first model-info request starts the first load. A Kiln whose user never asks for model info sends nothing to models.dev. There is no timer and no start-up load: a start-up load would add a 0.7 MB download to every app start, and the conditional GET makes a load on demand cheap. The only task is the refresh that a request starts; it can outlive that request, and `lifespan` cancels it at shutdown.
- **Bounded wait.** A request waits at most `wait_secs` (4 s) for models.dev, for a first load and for a reload. After that it answers with what there is, and the task goes on; the next request gets its result.
- **Single flight.** Between "is a task running" and `create_task` there is no `await`, so on one event loop no lock is needed. The other-loop guard matters only under Starlette's `TestClient` used without `with` (a new loop per request).
- **No network.** With no data ever loaded, the endpoints answer from Kiln's list: `models_dev.state` is `unavailable` and every price, limit and date is null. Rows, status, notes, tags and ranks are complete.
- **Request privacy.** The GET has no header of ours and no query string.
- **CPU.** The parse and the two indexes take 0.2-0.3 s, so they run in `asyncio.to_thread`. The dev server's `DEBUG_EVENT_LOOP` would report a stall.
- **Memory.** `parse_models_dev` keeps, per models.dev entry, only `cost` (`input`, `output`, `cache_read`, `cache_write`), `limit` (`context`, `output`), `temperature`, `release_date`, `knowledge`, `open_weights`, `reasoning` and `canonical_model_id`, in models.dev's own nesting, so HT's `_join` reads it unchanged. The 26 MB parsed document is dropped.

## 6. The join

### 6.1 Kiln's side

`read_kiln_model_list()` takes `tuple(built_in_models)` under `remote_config.refresh_lock` (the start-up thread replaces the list in place), `built_in_providers`, and the time of the last good remote load. For that time, `remote_config.py` gets a small holder beside `refresh_lock` (`@dataclass class RemoteModelListState: loaded_at: datetime | None = None`, one instance, a reader `remote_model_list_loaded_at()`), set inside the `with refresh_lock:` block of `refresh_model_list`. It is new module state beside the grandfathered `built_in_models` that it describes; say so in the PR.

Typed conversion (replaces HT's raw parse; Kiln's own deserializer already dropped what this client cannot run):

| Catalogue field | From |
|---|---|
| `model`, `display_name`, `family`, `kiln_featured_rank` | `KilnModel.name`, `.friendly_name`, `.family`, `.featured_rank` |
| `editorial_notes`, `agent_notes` | `_note(...)`: blank becomes null; over 2000 chars is cut and ends with ` [cut]` |
| `tags` (model, entry, provider) | `_tags(...)`: only `[a-z0-9_]{1,40}`, no duplicates, at most 12 |
| entry `provider`, `default_structured_output_mode` | `KilnModelProvider.name.value`, `.structured_output_mode.value` |
| entry `provider_model_id`, `deprecated`, `untested` | `.model_id`, `.deprecated`, `.untested_model` |
| entry `supports_tools`, `supports_structured_output`, `supports_vision` | `.supports_function_calling`, `.supports_structured_output`, `.supports_vision` |
| entry `thinking_levels`, `default_thinking_level` | the values of `.available_thinking_levels` in order; `.default_thinking_level` |
| entry `kiln_suggested_for` | `suggested_for_evals` -> `eval_judge`, `_data_gen` -> `synthetic_data`, `_doc_extraction` -> `document_extraction`, `_synthetic_user` -> `synthetic_user` |
| provider `provider`, `name`, `notes`, `tags`, `models_dev_id` | `KilnProviderInfo.id.value`, `.friendly_name`, `.notes`, `.tags`, `.models_dev_id` |

A duplicate model name: the first wins.

### 6.2 models.dev onto Kiln (HT `build.py:237-445`, unchanged)

1. **Provider mapping.** `KilnProviderInfo.models_dev_id` only. Null means "no models.dev entry": the entry is not joined. HT's fallback table is dropped, because every `ModelProviderName` has a `KilnProviderInfo`.
2. **Exact pair.** `providers[models_dev_id]["models"][provider_model_id]`. A match sets the entry's four prices (a finite number >= 0, not a bool; 0 is kept), `context_window` and `max_output_tokens` (an int > 0, not a bool) and `supports_temperature` (a bool, else null).
3. **Model facts.** From the first matched entry in the order `PREFERENCE = (openrouter, openai, anthropic, gemini_api, groq, together_ai)`, then the other providers by id: `release_date`, `knowledge_cutoff`, `open_weights`, `reasoning_model`, `context_window`, `max_output_tokens`.
4. **Median price.** Index over all of models.dev: `canonical_model_id` -> {models.dev provider -> its lowest price above 0}. The model uses the canonical id of the first matched entry that has one. The median is null with fewer than 3 priced providers. Input and output are separate.
5. **Loose release date.** Only when step 3 gave no date. Key: the last `/` segment, cut at `:`, lower case, `[a-z0-9]` only. Keys shorter than 4 are not used. The index maps a key to the earliest date among all models.dev entries with that key (from the model id and from the canonical id). The model takes the earliest date over all its entries, deprecated ones too, and sets `release_date_estimated`.
6. **Deprecation** is Kiln's per-entry flag. models.dev's `status` is not read. **Featured rank, notes, tags and suggested-for** are Kiln's values.

Edge cases: an entry with no `model_id` (2 today) is never joined and never `ready`. A model whose entries are all deprecated (45 today) shows only with `include_deprecated`. An exact match with no date falls back to the loose date. With `models_dev` null, step 6.2 is skipped whole.

### 6.3 The merge with what is offered (HT `_merged`, unchanged)

- Catalogue rows in Kiln's order, deep-copied.
- For an offered pair the catalogue has, the entry takes `thinking_levels`, `default_thinking_level` and `default_structured_output_mode` from the `/api/available_models` item (it forces `json_schema` for Ollama and Docker, and applies user overrides). Write these as three explicit assignments, not `setattr`.
- For an offered pair on a known model with no such entry, an entry is added from the item: flags, suggested-for, the three fields above. `provider_model_id` and the models.dev fields are null.
- Models that only the answer has are appended, sorted by id, `display_name` = the item's `name`. These are fine-tunes (`kiln_fine_tune`, id `<project>::<task>::<finetune>`), user models (`user_model::<uuid>`, under their provider), legacy custom models (`<provider>::<model>`), untested Ollama and Docker tags, and OpenAI-compatible server models (`<server name>::<model>`, provider `openai_compatible`). They have no rank, notes, price or date, and `untested` is true where Kiln says so.

## 7. Name search

Standard library only (`re`, `difflib`). For a text `t`: `spaced(t)` = lower case, each run of characters outside `[a-z0-9]` becomes one space, stripped; `squashed(t)` = lower case with those characters removed.

1. `q = squashed(search)`. Empty: `InvalidModelQueryError`.
2. For each row, with `i = squashed(model)` and `n = squashed(display_name)`, the rank is the first that holds: 0 when `q == i or q == n`; 1 when `i` or `n` starts with `q`; 2 when `q` is in `i` or in `n`; 3 when every word of `spaced(search)` is a substring of `spaced(model) + " " + spaced(display_name)` or of `i + " " + n`. No rank: the row does not match.
3. Some rows match: keep them; `fuzzy_match` is false. Order (when no `sort` is given): rank, then featured order.
4. No row matches: the typo pass. `ratio = max(SequenceMatcher(None, q, i).ratio(), SequenceMatcher(None, q, n).ratio())`. Keep rows with `ratio >= 0.75`, best first, ties in featured order. `fuzzy_match` is true when at least one row is kept.

Checked on the 314 built-in names: `sonnet 4.5` finds `claude_sonnet_4_5`; `gpt5 mini` and `gpt-5-mini` find `gpt_5_mini`; `llama3.1:8b` finds `llama_3_1_8b`; `4o mini` finds `gpt_4o_mini`; the typos `gemni flash` and `claud sonet` find the right families through step 4; `nova` finds nothing.

The search runs after the other filters. With the default filters it sees only what the user can run now, so an id lookup must pass `include_not_available=true` (section 9).

## 8. Wiring, the off switch, agent policy

```
# desktop_server.make_app, after connect_provider_api(app)
models_dev_cache = ModelsDevCache(enabled=not Config.shared().skip_models_dev)
app.state.models_dev_cache = models_dev_cache
connect_model_info_api(app, available_models=available_models, models_dev=models_dev_cache)

# desktop_server.lifespan, in the outer finally
cache = getattr(app.state, "models_dev_cache", None)
if cache is not None:
    await cache.aclose()
```

- **Off switch.** A new setting in `kiln_ai/utils/config.py`: `"skip_models_dev": ConfigProperty(bool, env_var="KILN_SKIP_MODELS_DEV", default=False, in_memory=True)`. It goes through `Config` because the conventions gate (`env-access`) allows new environment reads only in `Config` and the entry points, and `Config` parses booleans properly. It is separate from `KILN_SKIP_REMOTE_MODEL_LIST`; the facts show no blocker.
- **Tests.** The root `conftest.py` gets a second autouse fixture that sets `KILN_SKIP_MODELS_DEV=true` (with `monkeypatch.setenv`). `Config` reads the environment at each access, so every app a test builds has the cache off.
- **Dev server.** `dev_env.py`, the `dev_desktop` make target and `openapi_schema.sh` do not set the new variable. So the dev server still skips the remote Kiln list (`origin: built_in`) and gets live prices on the first model-info request. Building the app (schema dump, `make annotations`) sends nothing, because the load is lazy.
- **Agent policy.** `ALLOW_AGENT` on all three routes: read-only, no secret, no user data, the same policy as `/api/available_models`. After adding them: `make annotations` (writes `get_api_model_info_models.json`, `get_api_model_info_model_details.json`, `get_api_model_info_providers.json`), `make schema` (`api_schema.d.ts`), and the skill's API reference regenerated in the same change. CI `check_api_bindings` fails otherwise.

## 9. Mapping for the skill text

`query_params` values may be JSON booleans; a list repeats the key.

| Assistant tool | Method and path | `query_params` | Suggested `jq_filter` |
|---|---|---|---|
| `model_info_featured()` | `GET /api/model_info/models` | `{"featured": true, "include_notes": true, "include_not_available": true}` | `.models \| map({model, display_name, kiln_featured_rank, editorial_notes, agent_notes, median_input_price, median_output_price, context_window, ready_on: [.providers[] \| select(.status == "ready") \| .provider]})` |
| `model_info(model_id)` | `GET /api/model_info/model_details` | `{"model_id": "<id>"}` | none needed (about 1.5 k characters); `del(.sources)` to drop the source block |
| `model_search(query)` | `GET /api/model_info/models` | `{"search": "<words>", "include_not_available": true, "include_deprecated": true}` | `.models \| map({(.model): .display_name}) \| add` |

Points the skill text must carry: "featured" now means the ranked models (13 today), not "has editorial notes" (62), and tags give the wider sets (`recommended`, `top_value`, `top_fast`); the default list is what the user can run now; a null price is "no data", and `sources.models_dev.state` says why; the field names changed (`id` -> `model`, `name` -> `display_name`, `featured_rank` -> `kiln_featured_rank`, `providers[].id` -> `providers[].provider`, `providers[].model_id` -> `providers[].provider_model_id`, `supports_function_calling` -> `providers[].supports_tools`). New calls worth teaching: `{"sort": "price"}`; `{"tags": ["recommended"]}`; `GET /api/model_info/providers` with `.providers | map({provider, ready_model_count})`; `model_details` with `provider` and `.providers[0] | {thinking_levels, default_thinking_level, default_structured_output_mode}` before writing a run config.

## 10. Response size

The MCP tool's `body_limit` default is 30,000 characters (functional spec 5.6). Measured with HT's code on the real data (compact JSON):

| Answer | Characters |
|---|---|
| One row | 420-560 |
| List, `limit=25` (the default) | 10-13 k |
| List, `limit=50` | 21-25 k; 28 k with `include_not_available` |
| List, `limit=200` | 88-108 k |
| Details | 1.3-1.6 k |
| Providers, `include_not_available` | 5.1 k (21 rows) |

So 50 rows are close to the limit and 25 are safe. A second measurement with this document's response shape (the `sources` block is 196 characters; the note keys are present and null): the largest page of 25 over every offset, sort and flag was 18.1 k. With `include_notes` it was 23.9 k, and the featured list with notes (13 rows) 13.8 k. JSON with default separators is 6-9 % longer, so the largest page stays under 26 k. A caller that sets a higher `limit` is expected to add a `jq_filter`.

## 11. Python 3.10, dependencies, performance

- **Python 3.10.** HT needs 3.11. Its three 3.11-only points are all in `fetch.py`, which is rewritten: `datetime.UTC` -> `timezone.utc`; `asyncio.timeout` -> `asyncio.wait_for`; and on 3.10 `asyncio.TimeoutError` is not the builtin `TimeoutError`, so catch it by name. The ported code (`X | None`, walrus, `statistics.median`, `date.fromisoformat` on `YYYY-MM-DD`) runs on 3.10.
- **Type check and lint.** Replace `setattr(...)` and `**row.model_dump(include=...)` in the ported view code with explicit assignments and constructor calls. Use `Field(default_factory=list)`. Rewrite comments that name HT's spec sections, runs or probes.
- **Dependencies.** None new. `httpx` is already a dependency of core and server; the search uses `difflib`.
- **Performance (measured).** models.dev: 6.78 MB of JSON, about 0.70 MB gzipped, 1.2 s to download, `json.loads` 0.13 s, 324 providers and 10,024 entries. The join of 314 models (729 entries) against prebuilt indexes: 12 ms, and it runs only when a source changes. A reload on a normal day is one conditional GET. The search is 314 rows by two strings per call. The remaining cost per request is the `/api/available_models` logic, the same as the UI's own call.

## 12. Test plan

Tests sit beside the source. None patches a module: every dependency is passed in.

**Fixtures.** Copy HT's `tests/fixtures/model_catalog/models_dev.json` and `kiln_config.json` to `services/model_info/test_data/`. Load the Kiln slice through Kiln's own `deserialize_config_data` and validate its `provider_list` as `KilnProviderInfo` (checked: all 7 models and 5 providers validate).

**`test_catalog_build.py`** (port of HT `tests/test_model_catalog.py:74-500`, models built as `KilnModel`): prices, limits and dates from the fixture; price on the exact pair; model facts follow the provider preference; loose date (no exact match, earliest date, a deprecated entry counts, a short key is not used, an exact match with no date falls back); median (across every models.dev provider, needs three paid prices, a provider counts once at its lowest price, 0 left out); `kiln_suggested_for` names; `models_dev_id` is used; a provider without it is not joined; a bad price and a bad limit are dropped; tags cleaned and capped; a long note is cut; no models.dev gives null prices and Kiln's data; `parse_models_dev` on bad JSON and on a non-object. Not ported: the raw-parse cases (Kiln's deserializer owns them), the built-in map cases, the store cases.

**`test_models_dev.py`** (new). A `FakeClock` passed as `now`, and `client_factory` returning `httpx.AsyncClient(transport=httpx.MockTransport(handler))`; `wait_secs` and `fetch_timeout_secs` set to hundredths of a second where a stall is tested.
- first load gives `ok` data; the request has no `If-None-Match` and no header of ours;
- `enabled=False`: `unavailable` / `turned off`, and a `client_factory` that raises is never called;
- data younger than `max_age`: no request;
- stale data: one request with `If-None-Match`; a 304 keeps the data object and moves `loaded_at`; a 200 replaces data and ETag;
- each failure (non-200, timeout, transport error, over `max_bytes`, bad JSON, not an object) gives its reason and never raises; with no data the state is `unavailable`; with data it is `stale` and the data object is the old one;
- no new request before `retry_after_empty` (no data) or `retry_after` (data); one after it;
- single flight: 20 concurrent `current()` calls make one request;
- a stalled server: `current()` returns within `wait_secs` with `loading` (or `refresh running`), and after the handler is released the next call has the data;
- `aclose()` cancels a running refresh, and a later `current()` starts none;
- a task left over from another event loop is ignored.

**`test_view.py`** (port of HT `tests/test_gateway_model_info.py`, without the policy cases): the three statuses; `Offered` from a bad payload; ready entries only by default; `include_not_available`; deprecated left out by default; entry filters remove entries and then empty rows; a null value fails a filter; `reasoning_model` apart from thinking levels; the tag filter is ANY and a tag on an entry counts; price sort uses the median before the entries and a zero price never sorts; featured, price and newest with ties; paging and `total`; a pair the catalogue lacks; a model the catalogue lacks; server values win for an offered pair; details list every entry; provider counts and order; unconnected providers hidden by default. New: search ranks 0 to 3, the typo pass sets `fuzzy_match`, an empty result, search order against an explicit `sort`, a search with no letter or digit; `featured` true and false; `include_notes`; unknown provider; case-insensitive details lookup; closest ids in the not-found text; no models.dev data gives Kiln's rows with null prices.

**`test_service.py`** (new): the catalogue is rebuilt when the models.dev data object changes and when the Kiln list changes, and not otherwise; `sources` for `remote_config` and `built_in`, with ages from the fake clock.

**`test_model_info_api.py`** (new): `FastAPI()` + `connect_custom_errors` + `connect_model_info_api(app, available_models=fake, models_dev=FakeSource())` + `TestClient`. Query parsing (repeated `tags`, booleans, `limit` 0 and 201, 13 tags give 422); the 404 and 422 bodies of section 1.4; `sources` in all three answers; each route has `x-agent-policy` allow and no `x-mcp-policy` in `app.openapi()`.

**Edited files.** `test_provider_api.py`: `available_models()` returns what the route returns. `test_remote_config.py`: the load time is set on success and not on failure. `test_config.py`: `skip_models_dev` reads `KILN_SKIP_MODELS_DEV`. `test_dev_server.py`: the dev environment does not set it.

**No-network guarantee.** Three layers: the route, service and view tests get fakes and make no HTTP call; the cache tests use a mock transport; and for any test that builds the real app, the root fixture turns the cache off. One test asserts the last layer: `make_app()` under the test suite has `app.state.models_dev_cache.enabled is False`.

## 13. Open items

- **Legacy custom-model provider id (verify during implementation).** `/api/available_models` lists legacy custom models under `provider_id=openai_compatible`, `provider_name=kiln_custom_registry`, with id `<provider>::<model>`. Kiln's run code treats such ids only under `kiln_custom_registry`. Model info would show `openai_compatible` for them. Check that a run config with the pair the endpoint shows does run; if it does not, fix the provider id in `available_models()` before the skill tells agents to trust `provider`.
- **Follow-up: the web UI's own models.dev fetch.** `app/web_ui/src/routes/(app)/models/price.ts` fetches models.dev in the browser and uses Kiln's raw provider id with no mapping. It is out of scope here; it can move to these endpoints later.
- **All OpenAI-compatible servers share one provider id.** They are one `openai_compatible` row; the server name is only inside the model id. A `provider_name` field on the entry is a possible later addition.
- **Fine-tunes are bound to a task.** `task_filter` is not carried, so an agent could pick a fine-tune of another task. Decide whether to add the field or to say it in the skill.
- **Search under the default filters.** A search for a model on an unconnected provider gives nothing unless `include_not_available` is set. The skill mapping sets it; a hint field ("N more with include_not_available") is a possible addition.
- **Cost of the availability check.** Each request runs the `/api/available_models` logic: synchronous `requests` calls to Ollama on the event loop (up to 5 s for an unreachable custom host) and a disk walk for fine-tunes. Existing behaviour; a cache of a few seconds is an easy later change.
- **Kiln's list is as old as the app start**, and provider notes and `models_dev_id` values are as old as the installed version. `sources.kiln_model_list` reports the first; nothing reloads either.
- **Decisions made here that the binding file did not give**, for a person to confirm: the off switch as a `Config` setting named `skip_models_dev` / `KILN_SKIP_MODELS_DEV`; the 4 s wait also for a reload of stale data; the shorter retry interval (1 minute) while there is no data; 422 on an unknown provider id; `featured=false` as the complement; the `ModelInfo` prefix on every response class; the catalogue memo in `ModelInfoService`.
- **`include_notes` has no hard size bound.** Notes can be 2000 characters each. Today's longest are 259 and 430, and the measured pages fit; a much longer set of notes in the remote config could pass 30,000 characters at `limit=25`.
- **Two copies until harness-tuner adopts the endpoints.** Fixes to the join must go to both, or HT's copy is frozen.
- **Unverified:** the size in memory of the slim models.dev form (estimate: a few MB); whether `ty` and ruff reject HT's `setattr` and `**model_dump` forms (they are rewritten anyway); how the hosted Assistant matches these paths to its annotations; models.dev's terms of use for a desktop app that fetches the file.
