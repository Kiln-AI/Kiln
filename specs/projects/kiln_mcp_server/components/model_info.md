---
status: draft
---

# Component: Model info endpoints

Three read-only REST endpoints that join Kiln's model list with the public models.dev catalogue (functional spec section 8). They are a port of harness-tuner's model info code (HT below; paths under `harness-tuner/src/kiln_harness_tuner/`), without HT's model policy and without its per-run snapshot. Every "as HT" in this doc, and every HT line reference, means harness-tuner at commit `b49f159`, the same pinned commit as the knowledge port (skill doc, section 9). Agents reach the endpoints through `call_kiln_api`; the web UI and other clients may use them too. This is build step 3 of [architecture.md](../architecture.md) section 6; shared files are in its section 9.

Out of scope: a reload of Kiln's own model list (it still loads once at app start), a disk cache, and the web UI's own models.dev fetch.

## 1. Endpoints

All three routes: `tags=["Providers & Models"]`, `openapi_extra=ALLOW_AGENT`, no `x-mcp-policy` tag, a `summary`, and a docstring written for API readers. Every answer has a `sources` block (section 2). Parameters use `Annotated[..., Query(description=...)]`, as `libs/server/kiln_server/memory_api.py` does. A list parameter repeats the key.

### 1.1 `GET /api/model_info/models`

| Parameter | Type | Default | Validation | Meaning |
|---|---|---|---|---|
| `search` | str | none | 1-100 chars | Name search on the model id and display name (section 7). |
| `featured` | bool | none | | `true`: only models with a `kiln_featured_rank`. `false`: only models without one. |
| `provider` | str | none | 1-200 chars | Kiln provider id. Keeps only that provider's entries. |
| `family` | str | none | 1-100 chars | Exact match on `family`. |
| `tags` | list[str] | none | at most 12, each 1-40 chars | A row passes when it has ANY of these tags, on the model or on a kept provider entry. |
| `supports_tools`, `supports_vision`, `has_thinking_levels` | bool | none | | Entry filters. |
| `reasoning_model`, `open_weights` | bool | none | | Row filters (models.dev facts). |
| `include_not_available` | bool | `false` | | Also list entries whose status is not `ready`. |
| `include_deprecated` | bool | `false` | | Also list deprecated entries. |
| `include_notes` | bool | `false` | | Fill `editorial_notes` and `agent_notes` in each row. |
| `sort` | `featured`, `price` or `newest` | none | | See step 5. |
| `limit` | int | `25` | 1-200 | Page size. |
| `offset` | int | `0` | >= 0 | Rows to skip. |

The defaults are decisions: the list shows only what the user can run now (entries with status `ready`, not deprecated) unless the caller asks for more, and `featured=false` is the complement of `featured=true`. The providers route (1.3) has no such default: it lists every provider, each marked connected or not.

Steps, in this order:

1. Build the merged rows (section 6.3).
2. Entry filters. An entry is kept when: its status is `ready`, or `include_not_available` is true; it is not deprecated, or `include_deprecated` is true; `provider` is not given or equals the entry's provider; each given entry filter equals the entry's value (`has_thinking_levels` compares with `bool(entry.thinking_levels)`). A null value fails a filter that tests it, for `true` and for `false`.
3. Row filters. A row is kept when: at least one entry is left; `family` matches; `open_weights` and `reasoning_model` equal the given values (null fails); `featured` matches; `tags` matches (ANY).
4. Search (section 7), on the rows left after step 3.
5. Sort. The base order is Kiln's list order, then the models that only `/api/available_models` knows, by id. A stable sort by featured rank always runs first (ranked rows by rank, then the rest in base order). Then:
   - `sort=price`: ascending by `median_input_price + median_output_price`; when either is null, by the cheapest kept entry that has both prices above 0; rows with no price go last. A price of 0 never sorts.
   - `sort=newest`: `release_date` descending; rows with no date go last.
   - `sort=featured`, or no `sort` and no `search`: nothing more.
   - no `sort` with `search`: best match first, ties in featured order. An explicit `sort` with `search` uses that sort and ignores the match rank.
6. Page: `rows[offset : offset + limit]`. `total` is the row count after step 4, the same on every page. An `offset` past the end gives an empty `models` list.
7. A row lists only its kept entries. `has_thinking_levels` is computed over the kept entries.

### 1.2 `GET /api/model_info/model_details`

Parameters: `model_id` (str, required, 1-200 chars: a Kiln model id) and `provider` (str, optional, 1-200 chars: keep only this provider's entry). The id is a query parameter because ids of custom, fine-tuned and local models hold `::`, `:` and `/`, and a path segment cannot carry `/`.

Lookup over the merged rows, with no status or deprecation filter:

1. A row whose `model` equals `model_id`.
2. Else the rows whose `model.casefold()` equals `model_id.casefold()`. One row: use it. The answer's `model` field has the correct spelling.
3. Else, or with more than one row in step 2: 404.
4. With `provider`: keep the entries whose provider equals it exactly. None left: 404.

### 1.3 `GET /api/model_info/providers`

No parameter. The route lists every provider, each marked `connected` or `not_connected` (functional spec 8); nothing is hidden, so an agent can tell the user which provider to connect. Provider ids: the built-in provider list, then providers seen in model entries, then connected providers, without duplicates. Order: `ready_model_count` descending, then id, so the connected providers with models come first.

### 1.4 Errors

Kiln's error handler turns `HTTPException.detail` into `{"message": ...}`. FastAPI validation errors (a missing `model_id`, `limit=0`, 13 tags, a bad boolean) are 422 in Kiln's usual shape.

| Case | Status | `message` |
|---|---|---|
| Unknown model | 404 | `Model not found: <id>. Closest ids: <a>, <b>, <c>. To find a model id, call GET /api/model_info/models with search=<name> and include_not_available=true.` The `Closest ids` sentence is left out when there is none. |
| Model has no entry for `provider` | 404 | `Model <model> has no entry for provider <provider>. Its providers: <a>, <b>.` |
| `provider` on the list route is not a known provider id | 422 | `Unknown provider: <provider>. Provider ids: <sorted ids>.` |
| `search` holds no letter and no digit | 422 | `search needs at least one letter or digit.` |

Closest ids: the first three ids that the search of section 7 gives for `model_id` over all merged rows. Known provider ids are those of section 1.3. Both 422 cases are decisions. The 422 on an unknown provider exists because a wrong id (`google` for `gemini_api`) would otherwise give an empty list that reads as "no such models".

## 2. Response models

File `app/desktop/studio_server/api_models/model_info_models.py`. Plain `BaseModel` classes; list fields use `Field(default_factory=list)`. Every class name starts with `ModelInfo`, because `provider_api.py` already defines `ModelDetails`, `AvailableModels` and `ProviderModels`, and names are global in the OpenAPI schema. Keep HT's field descriptions (`gateway/models.py:123-136`): they reach the agent through the generated API reference. All prices are USD per million tokens; null means "no price data", not "free".

**`ModelInfoSources`**: `kiln_model_list: ModelInfoKilnSource`, `models_dev: ModelInfoModelsDevSource`.

| Class | Field | Type | Meaning |
|---|---|---|---|
| `ModelInfoKilnSource` | `origin` | `"remote_config"` or `"built_in"` | `remote_config`: the remote list was loaded in this process. `built_in`: the list shipped with the installed app (offline at start, skipped, or failed). |
| | `loaded_at`, `age_seconds` | datetime or null, int or null | UTC time of the last good remote load, and now minus that. Null for `built_in`. |
| `ModelInfoModelsDevSource` | `state` | `"ok"`, `"stale"` or `"unavailable"` | `ok`: data younger than 6 h. `stale`: older data is served. `unavailable`: no data; every models.dev field is null. |
| | `loaded_at`, `age_seconds` | datetime or null, int or null | UTC time the data was fetched, or last confirmed unchanged by a 304, and now minus that. |
| | `detail` | str or null | Null when `ok`. Else `turned off`, `loading`, `not loaded`, `refresh running`, or the last failure reason (section 5.3). |

**`ModelInfoList`**: `sources`; `total: int` (rows after all filters); `fuzzy_match: bool` (true: no model held the search words, and the rows are the closest names); `models: list[ModelInfoRow]`.

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

**`ModelInfoProviderEntryRow`**: `provider: str` (Kiln provider id), `status: ModelInfoStatus`, `input_price` and `output_price` (float or null), `tags: list[str]`, `deprecated: bool`.

**`ModelInfoDetails`**: `sources`, every `ModelInfoRow` field (notes always filled; `has_thinking_levels` over the listed entries), `release_date_estimated: bool` (true: the date came from a match on the model's name only), `knowledge_cutoff: str | None` (as models.dev writes it), `max_output_tokens: int | None`, and `providers: list[ModelInfoProviderEntryDetails]` (every entry, also deprecated and not available ones).

| `ModelInfoProviderEntryDetails` field | Type | Meaning |
|---|---|---|
| `provider`, `status`, `input_price`, `output_price`, `tags`, `deprecated` | as in the entry row | |
| `provider_model_id` | str or null | The provider's own id for the model. Null for an entry that came from `/api/available_models`. |
| `untested` | bool | Kiln has not tested this model, usually one a user added. The `supports_*` fields do not apply. |
| `cache_read_price`, `cache_write_price` | float or null | From models.dev. |
| `context_window`, `max_output_tokens` | int or null | This provider's limits, from models.dev. |
| `supports_tools`, `supports_structured_output`, `supports_vision` | bool or null | Kiln's flags for the pair. |
| `supports_temperature` | bool or null | From models.dev. |
| `thinking_levels`, `default_thinking_level` | list[str], str or null | The values a run config can set, in Kiln's order, and the default. |
| `default_structured_output_mode` | str or null | Kiln's suggested default output mode for the pair. |
| `kiln_suggested_for` | list[str] | Any of `eval_judge`, `synthetic_data`, `document_extraction`, `synthetic_user`. |

**`ModelInfoProviderList`**: `sources`, `providers: list[ModelInfoProviderRow]`.

| `ModelInfoProviderRow` field | Type | Meaning |
|---|---|---|
| `provider`, `name` | str, str or null | Kiln provider id, and the friendly name from `built_in_providers`. |
| `status` | `"connected"` or `"not_connected"` | Connected: the provider is in the `/api/available_models` answer. |
| `ready_model_count` | int | Pairs on this provider with status `ready`. It counts deprecated and untested pairs too; the description says so. |
| `tags`, `notes` | list[str], str or null | Kiln's provider tags and notes (data retention, rate limits). |

**`ModelInfoStatus`** `= Literal["ready", "not_offered", "not_connected"]`, computed at every request from one in-process call of the `/api/available_models` logic (section 4):

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
| `api_models/model_info_models.py` | `gateway/models.py:120-262` | Port. Drop `blocked_by_policy`; `sources` replaces `catalog`; add the notes on the row and `fuzzy_match`. HT's request models become query parameters. |
| `services/model_info/catalog_schema.py` | `model_catalog/schema.py` | Port nearly unchanged: `CatalogEntry`, `CatalogModel`, `CatalogProvider`, `Catalog` (only `models`, `providers`, `.model()`, `.provider()`). Drop `Source`, `fetched_at`, `Catalog.unavailable`. |
| `services/model_info/catalog_build.py` | `model_catalog/build.py` | Lines 237-445 (join, median, loose date) port unchanged. Lines 58-234 (the tolerant parse of the published JSON) are replaced by a typed conversion from Kiln's objects. `_note`, `_tags`, `KILN_SUGGESTED_FOR`, `PREFERENCE` are kept. |
| `services/model_info/models_dev.py` | `model_catalog/fetch.py` (reason strings only) | Rewrite: `ModelsDevCache` (section 5). |
| `services/model_info/view.py` | `gateway/model_info.py` | Port: `Offered`, `status` (no policy argument), `_merged`, the filters, the sorts, the three answers. New: search, `featured`, `include_notes`, the forgiving lookup, two domain errors. |
| `services/model_info/service.py` | none | New: `ModelInfoService`, which gathers the inputs of each request. |

Dropped from HT: `store.py`, `providers.py` except `PREFERENCE`, `model_policy.py`, `--no-model-catalog`. Edited Kiln files: `provider_api.py` (section 4), `desktop_server.py`, `kiln_ai/utils/config.py` and the root `conftest.py` (section 8), `kiln_ai/adapters/remote_config.py` (section 6.1). The first three are also edited by the MCP server component; architecture section 9 has the combined result and says who changes what.

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
    loaded_at: datetime | None                 # None: the built-in list
def read_kiln_model_list() -> KilnModelList    # section 6.1
class ModelInfoService:
    def __init__(self, *, available_models: AvailableModelsFn, models_dev: ModelsDevSource,
                 kiln_model_list: Callable[[], KilnModelList] = read_kiln_model_list,
                 now: Callable[[], datetime] = utc_now) -> None
    async def list_models(self, query: ListModelsQuery) -> ModelInfoList
    async def model_details(self, model_id: str, provider: str | None) -> ModelInfoDetails
    async def list_providers(self) -> ModelInfoProviderList

# services/model_info/view.py   (pure functions)
class ListModelsQuery                          # frozen dataclass: one field per parameter of 1.1, same names and defaults
class ModelNotFoundError(Exception)            # str(error) is the message of 1.4
class InvalidModelQueryError(Exception)
class Offered                                  # as HT: pairs, connected, order; Offered.from_payload(payload: Any)
def status(offered: Offered, provider: str, model: str) -> ModelInfoStatus
def list_models(catalog: Catalog, offered: Offered, sources: ModelInfoSources, query: ListModelsQuery) -> ModelInfoList
def model_details(catalog, offered, sources, model_id: str, provider: str | None) -> ModelInfoDetails
def list_providers(catalog, offered, sources) -> ModelInfoProviderList
def search_rows(query: str, rows: Sequence[CatalogModel]) -> tuple[list[CatalogModel], bool]   # (best first, fuzzy)

# services/model_info/catalog_build.py   (pure functions)
@dataclass(frozen=True)
class ModelsDevData:
    providers: Mapping[str, Any]               # models.dev's shape, with only the keys the join reads
    loose_dates: Mapping[str, str]             # loose key -> earliest release date
    canonical_prices: Mapping[str, Prices]     # HT's _Prices
def parse_models_dev(body: bytes) -> ModelsDevData   # ValueError("not valid JSON") or ValueError("not an object")
def build_catalog(kiln: KilnModelList, models_dev: ModelsDevData | None) -> Catalog
```

Each service method does: `kiln = self._kiln_model_list()`; `snapshot = await self._models_dev.current()`; `offered = Offered.from_payload([p.model_dump(mode="json") for p in await self._available_models()])`; `catalog = self._catalog(kiln, snapshot.data)`; build `sources` (ages from `now`); call the view function. `_catalog` keeps the last built catalogue and reuses it while `snapshot.data` is the same object and `kiln.models` holds the same objects in the same order (compare with `is`; the kept tuple keeps the objects alive, so an id cannot be reused). The view functions never change the catalogue: `_merged` works on deep copies, as in HT.

## 4. The `/api/available_models` refactor

The logic is a closure inside `connect_provider_api` today (`provider_api.py:282-407`), so nothing else can call it. The exact change:

1. Add a module-level `async def available_models() -> List[AvailableModels]` directly above `connect_provider_api`. Its body is the body of `get_available_models`, unchanged, except that the local variable `available_models` (in the built-in model loop) is renamed to `provider_models`, because it would shadow the function's own name. The body uses module-level names only, so nothing else changes.
2. The route handler becomes `return await available_models()`.
3. `model_info_api.py` does not import `provider_api.py` ("routers are not libraries"). `desktop_server.make_app`, which already imports every router, passes the function in (section 8).
4. Existing tests patch module-level helpers of `provider_api` (`available_ollama_models`, `Config`, ...) and keep working. The service reads the payload as plain dicts through `Offered.from_payload`, so HT's tolerant reader and its tests port unchanged, and `view.py` needs no type from `provider_api.py`.

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

class ModelsDevSource(Protocol):               # async def current(self) -> ModelsDevSnapshot
class ModelsDevCache:                          # implements ModelsDevSource
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
    async def current(self) -> ModelsDevSnapshot     # never raises
    async def settle(self) -> None                   # waits for a refresh in flight, if any; for tests
    async def aclose(self) -> None                   # cancels a refresh in flight; later calls start none; never raises
```

The constructor does no I/O and creates no asyncio object. Fields: `_data`, `_etag`, `_loaded_at`, `_last_failure`, `_last_failure_at`, `_task: asyncio.Task | None`, `_closed`. `default_client()` returns `httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=True)`; one short-lived client per refresh. Memory only: no disk cache.

### 5.2 State machine

The state is derived from the fields; it is not stored. `aclose()` from any state cancels the task, and no new task starts. The "Request waits" column is the rule of 5.3: only a first load, with no data at all, makes a request wait.

| State | Condition | Answer `state` / `detail` | Request waits | Leaves on |
|---|---|---|---|---|
| off | `enabled` is false | `unavailable` / `turned off` | no | never |
| empty | no data, no task | `unavailable` / the last failure reason, or `not loaded` | no; a call that starts the load waits as in "loading" | `current()` -> loading, unless a failure is younger than `retry_after_empty` |
| loading | no data, a task runs | `unavailable` / `loading` | up to `wait_secs` for the task | 200 with a valid body -> fresh; any failure -> empty |
| fresh | data, age < `max_age` | `ok` / null | no | 6 h pass -> stale |
| stale | data, age >= `max_age`, no task | `stale` / the last failure reason, or null | no | `current()` -> refreshing, unless a failure is younger than `retry_after`. The call that starts the refresh is answered at once from the stale data |
| refreshing | data, age >= `max_age`, a task runs | `stale` / `refresh running` | no: answered at once from the stale data | 200 -> fresh (new data, new ETag); 304 -> fresh (same data, `loaded_at` = now); any failure -> stale (last good data kept) |

The retry intervals (`retry_after` 10 minutes with data, `retry_after_empty` 1 minute without) are decisions.

### 5.3 `current()` and the refresh

```
current():
  if not enabled: return the "off" snapshot
  now = self._now()
  if (no data or now - loaded_at >= max_age) and not closed:
      task = self._task, or None when it is done or belongs to another event loop
      if task is None and (no failure, or now - last_failure_at >= the retry interval of the state):
          task = self._task = asyncio.create_task(self._refresh())      # single flight: one task at a time
      if task is not None and no data:                       # only a first load waits
          await asyncio.wait({task}, timeout=wait_secs)      # a timeout does not cancel the task
      # with stale data: no await. The refresh runs in the background; this call answers from the stale data
  return the snapshot for the fields as they are now

settle():     # tests only
  task = self._task
  if task is not None and not task.done(): await asyncio.wait({task})

_refresh():   # never raises, except CancelledError
  await asyncio.wait_for(self._fetch(), fetch_timeout_secs)
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

- **Lazy, no background loop.** The first model-info request starts the first load. A Kiln whose user never asks for model info sends nothing to models.dev. There is no timer and no start-up load: a start-up load would add a 0.7 MB download to every app start, and the conditional GET makes a load on demand cheap. The only task is the refresh that a request starts; it can outlive that request, and `lifespan` cancels it at shutdown.
- **Stale data is served at once.** When data exists but is older than `max_age`, the request is answered at once from that data (`state: stale`), and a single background refresh is started. The request does not wait for it; a later request gets the new data.
- **Bounded wait, first load only.** Only a first load, with no data at all, makes a request wait: at most `wait_secs` (4 s). Then it answers from Kiln's own list (`state: unavailable`, `detail: loading`); the task goes on, and the next request gets its result.
- **Single flight.** Between "is a task running" and `create_task` there is no `await`, so on one event loop no lock is needed. The other-loop guard matters only under Starlette's `TestClient` used without `with` (a new loop per request).
- **No network.** With no data ever loaded, the endpoints answer from Kiln's list: `models_dev.state` is `unavailable` and every price, limit and date is null. Rows, status, notes, tags and ranks are complete.
- **Privacy and CPU.** The GET has no header of ours and no query string. The parse and the two indexes take 0.2-0.3 s, so they run in `asyncio.to_thread`.
- **Memory.** `parse_models_dev` keeps, per models.dev entry, only `cost` (`input`, `output`, `cache_read`, `cache_write`), `limit` (`context`, `output`), `temperature`, `release_date`, `knowledge`, `open_weights`, `reasoning` and `canonical_model_id`, in models.dev's own nesting, so HT's `_join` reads it unchanged. The 26 MB parsed document is dropped.

## 6. The join

### 6.1 Kiln's side

`read_kiln_model_list()` takes `tuple(built_in_models)` under `remote_config.refresh_lock` (the start-up thread replaces the list in place), `built_in_providers`, and the time of the last good remote load. For that time, `remote_config.py` gets a small holder beside `refresh_lock` (`@dataclass class RemoteModelListState: loaded_at: datetime | None = None`, one instance, and a reader `remote_model_list_loaded_at()`), set inside the `with refresh_lock:` block of `refresh_model_list`. It is new module state beside the grandfathered `built_in_models` that it describes; say so in the PR.

The typed conversion replaces HT's raw parse (Kiln's own deserializer already dropped what this client cannot run). A duplicate model name: the first wins.

| Catalogue field | From |
|---|---|
| `model`, `display_name`, `family`, `kiln_featured_rank` | `KilnModel.name`, `.friendly_name`, `.family`, `.featured_rank` |
| `editorial_notes`, `agent_notes`, provider `notes` | `_note(...)`: blank becomes null; over 2000 chars is cut and ends with ` [cut]` |
| `tags` (model, entry, provider) | `_tags(...)`: only `[a-z0-9_]{1,40}`, no duplicates, at most 12 |
| entry `provider`, `default_structured_output_mode` | `KilnModelProvider.name.value`, `.structured_output_mode.value` |
| entry `provider_model_id`, `deprecated`, `untested` | `.model_id`, `.deprecated`, `.untested_model` |
| entry `supports_tools`, `supports_structured_output`, `supports_vision` | `.supports_function_calling`, `.supports_structured_output`, `.supports_vision` |
| entry `thinking_levels`, `default_thinking_level` | the values of `.available_thinking_levels` in order; `.default_thinking_level` |
| entry `kiln_suggested_for` | `suggested_for_evals` -> `eval_judge`, `_data_gen` -> `synthetic_data`, `_doc_extraction` -> `document_extraction`, `_synthetic_user` -> `synthetic_user` |
| provider `provider`, `name`, `models_dev_id` | `KilnProviderInfo.id.value`, `.friendly_name`, `.models_dev_id` |

### 6.2 models.dev onto Kiln (HT `build.py:237-445`, unchanged)

1. **Provider mapping.** `KilnProviderInfo.models_dev_id` only. Null means "no models.dev entry": the entry is not joined. HT's fallback table is dropped, because every `ModelProviderName` has a `KilnProviderInfo`.
2. **Exact pair.** `providers[models_dev_id]["models"][provider_model_id]`. A match sets the entry's four prices (a finite number >= 0, not a bool; 0 is kept), `context_window` and `max_output_tokens` (an int > 0, not a bool) and `supports_temperature` (a bool, else null).
3. **Model facts.** From the first matched entry in the order `PREFERENCE = (openrouter, openai, anthropic, gemini_api, groq, together_ai)`, then the other providers by id: `release_date`, `knowledge_cutoff`, `open_weights`, `reasoning_model`, `context_window`, `max_output_tokens`.
4. **Median price.** Index over all of models.dev: `canonical_model_id` -> {models.dev provider -> its lowest price above 0}. The model uses the canonical id of the first matched entry that has one. The median is null with fewer than 3 priced providers. Input and output are separate.
5. **Loose release date.** Only when step 3 gave no date. Key: the last `/` segment, cut at `:`, lower case, `[a-z0-9]` only. Keys shorter than 4 are not used. The index maps a key to the earliest date among all models.dev entries with that key (from the model id and from the canonical id). The model takes the earliest date over all its entries, deprecated ones too, and sets `release_date_estimated`.
6. **Deprecation** is Kiln's per-entry flag; models.dev's `status` is not read. **Featured rank, notes, tags and suggested-for** are Kiln's values.

Edge cases: an entry with no `model_id` (2 today) is never joined and never `ready`. A model whose entries are all deprecated (45 today) shows only with `include_deprecated`. An exact match with no date falls back to the loose date. With no models.dev data, none of these steps runs.

### 6.3 The merge with what is offered (HT `_merged`, unchanged)

- Catalogue rows in Kiln's order, deep-copied.
- For an offered pair the catalogue has, the entry takes `thinking_levels`, `default_thinking_level` and `default_structured_output_mode` from the `/api/available_models` item (it forces `json_schema` for Ollama and Docker, and applies user overrides). Write these as three explicit assignments, not `setattr`.
- For an offered pair on a known model with no such entry, an entry is added from the item: flags, suggested-for, the three fields above. `provider_model_id` and the models.dev fields are null.
- Models that only the answer has are appended, sorted by id, `display_name` = the item's `name`. These are fine-tunes (`kiln_fine_tune`, id `<project>::<task>::<finetune>`), user models (`user_model::<uuid>`, under their provider), legacy custom models (`<provider>::<model>`), untested Ollama and Docker tags, and OpenAI-compatible server models (`<server name>::<model>`, provider `openai_compatible`). They have no rank, notes, price or date, and `untested` is true where Kiln says so.
- Two known limits, accepted. All OpenAI-compatible servers share one provider id, so they are one `openai_compatible` row in the providers list, and the server name is only inside the model id. A fine-tune is bound to a task, and `task_filter` is not carried, so the list can show a fine-tune of another task; the skill text carries the rule (section 9).

## 7. Name search

Standard library only (`re`, `difflib`). For a text `t`: `spaced(t)` = lower case, each run of characters outside `[a-z0-9]` becomes one space, stripped; `squashed(t)` = lower case with those characters removed.

1. `q = squashed(search)`. Empty: `InvalidModelQueryError`.
2. For each row, with `i = squashed(model)` and `n = squashed(display_name)`, the rank is the first that holds: 0 when `q == i or q == n`; 1 when `i` or `n` starts with `q`; 2 when `q` is in `i` or in `n`; 3 when every word of `spaced(search)` is a substring of `spaced(model) + " " + spaced(display_name)` or of `i + " " + n`. No rank: the row does not match.
3. Some rows match: keep them; `fuzzy_match` is false. Order (when no `sort` is given): rank, then featured order.
4. No row matches: the typo pass. `ratio = max(SequenceMatcher(None, q, i).ratio(), SequenceMatcher(None, q, n).ratio())`. Keep rows with `ratio >= 0.75`, best first, ties in featured order. `fuzzy_match` is true when at least one row is kept.

Checked on the 314 built-in names: `sonnet 4.5` finds `claude_sonnet_4_5`; `gpt5 mini` and `gpt-5-mini` find `gpt_5_mini`; `llama3.1:8b` finds `llama_3_1_8b`; `4o mini` finds `gpt_4o_mini`; the typos `gemni flash` and `claud sonet` find the right families through step 4; `nova` finds nothing. The search runs after the other filters, so with the default filters it sees only what the user can run now. An id lookup must pass `include_not_available=true` (section 9).

## 8. Wiring, the off switch, agent policy

```
# desktop_server.make_app, directly after connect_provider_api(app)
models_dev_cache = ModelsDevCache(enabled=not Config.shared().skip_models_dev)
app.state.models_dev_cache = models_dev_cache
connect_model_info_api(app, available_models=available_models, models_dev=models_dev_cache)

# desktop_server.lifespan, in the outer finally, after job_registry.events.shutdown()
# and before the inner try that stops the background syncs
cache = getattr(app.state, "models_dev_cache", None)
if cache is not None:
    await cache.aclose()
```

- **Shared file.** The MCP server component edits the same two functions. The combined `make_app` and `lifespan` are in architecture section 9.1, and that is the text to build from. For this component: the router can be anywhere after `connect_provider_api(app)` (it must come before `connect_kiln_mcp_server`, which is last so that its route index sees these routes); the `aclose()` call is the only line this component adds to the `finally` block, and `aclose()` never raises, so the lines after it still run.

- **Off switch.** A new setting in `kiln_ai/utils/config.py`: `"skip_models_dev": ConfigProperty(bool, env_var="KILN_SKIP_MODELS_DEV", default=False, in_memory=True)`. It goes through `Config` because the conventions gate (`env-access`) allows new environment reads only in `Config` and the entry points, and `Config` parses booleans properly. It is separate from `KILN_SKIP_REMOTE_MODEL_LIST`; the facts show no blocker.
- **Tests.** The root `conftest.py` gets one new autouse fixture, `skip_models_dev`, beside the existing `skip_remote_model_list`. It sets `KILN_SKIP_MODELS_DEV=true` (`monkeypatch.setenv`) and imports nothing. `Config` reads the environment at each access, so every app a test builds has the cache off. It is the only fixture this project adds to the root `conftest.py`; the MCP server's fixture, `kiln_mcp_tmp_root`, is in `app/desktop/conftest.py` (architecture section 9.2).
- **Dev server.** `dev_env.py`, the `dev_desktop` make target and `openapi_schema.sh` do not set the new variable. So the dev server still skips the remote Kiln list (`origin: built_in`) and gets live prices on the first model-info request. Building the app (schema dump, `make annotations`) sends nothing, because the load is lazy.
- **Agent policy.** `ALLOW_AGENT` on all three routes: read-only, no secret, no user data, the same policy as `/api/available_models`. They are not MCP-blocked. After adding them, in the same change: `make annotations` (writes `get_api_model_info_models.json`, `get_api_model_info_model_details.json`, `get_api_model_info_providers.json`) and `make schema` (`api_schema.d.ts`); the existing `check_api_bindings` workflow checks both. The skill's API reference is not regenerated in this step: its pipeline does not exist until build step 4, and the reference is generated there for the first time, with these three endpoints in it.
- **The hosted Kiln Assistant.** The three annotation files are how the hosted Assistant service learns that it may call these routes. It picks them up when it next updates its Kiln version. Nothing is done in the hosted service in this project (architecture section 8).

## 9. Mapping for the skill text

`query_params` values may be JSON booleans; a list repeats the key. In the table, `\|` stands for `|`.

| Assistant tool | Method and path | `query_params` | Suggested `jq_filter` |
|---|---|---|---|
| `model_info_featured()` | `GET /api/model_info/models` | `{"featured": true, "include_notes": true, "include_not_available": true}` | `.models \| map({model, display_name, kiln_featured_rank, editorial_notes, agent_notes, median_input_price, median_output_price, context_window, ready_on: [.providers[] \| select(.status == "ready") \| .provider]})` |
| `model_info(model_id)` | `GET /api/model_info/model_details` | `{"model_id": "<id>"}` | none needed (about 1.5 k characters); `del(.sources)` drops the source block |
| `model_search(query)` | `GET /api/model_info/models` | `{"search": "<words>", "include_not_available": true, "include_deprecated": true}` | `.models \| map({(.model): .display_name}) \| add` |

Points the skill text must carry: "featured" now means the ranked models (13 today), not "has editorial notes" (62), and tags give the wider sets (`recommended`, `top_value`, `top_fast`); the default list is what the user can run now; a fine-tune's id names its project and task (`<project>::<task>::<finetune>`), and a fine-tune is used only for its own task; when a model's provider is `not_connected`, the agent asks the user to connect it in the app (skill doc 4.4); a null price is "no data", and `sources.models_dev.state` says why; the field names changed (`id` -> `model`, `name` -> `display_name`, `featured_rank` -> `kiln_featured_rank`, `providers[].id` -> `providers[].provider`, `providers[].model_id` -> `providers[].provider_model_id`, `supports_function_calling` -> `providers[].supports_tools`). New calls worth teaching: `{"sort": "price"}`; `{"tags": ["recommended"]}`; `GET /api/model_info/providers` with `.providers | map({provider, status, ready_model_count})`; `model_details` with `provider` and `.providers[0] | {thinking_levels, default_thinking_level, default_structured_output_mode}` before writing a run config.

## 10. Response size

The MCP tool's `body_limit` default is 30,000 characters (functional spec 5.6). The facts file measured HT's code on the real data: one row is 420-560 characters; a list with `limit=25` is 10-13 k; with `limit=50` it is 21-25 k, and 28 k with `include_not_available`; with `limit=200` it is 88-108 k; one details answer is 1.3-1.6 k; the full providers list, unconnected providers included, is 5.1 k (21 rows). So 50 rows are close to the limit and the default of 25 is safe.

A second measurement on the same data with this document's response shape (the `sources` block is 196 characters; the note keys are present and null) took the largest page of 25 over every offset, sort and flag: 18.1 k as compact JSON, which is the form the MCP tool measures (`mcp_server_and_api_tool.md`), and 19.8 k with default separators. With `include_notes`: 23.9 k and 25.5 k. The featured list with notes (13 rows) is 13.8 k. A caller that sets a higher `limit` is expected to add a `jq_filter`.

`include_notes` has no hard size bound, and this is accepted. A note can be 2000 characters (6.1). Today's longest are 259 and 430, and the measured pages fit. Much longer notes in the remote config could pass 30,000 characters at `limit=25`; the agent then gets the "Body too long" error, which says what to do.

## 11. Python 3.10, dependencies, performance

- **Python 3.10.** HT needs 3.11. Its three 3.11-only points are all in `fetch.py`, which is rewritten: `datetime.UTC` -> `timezone.utc`; `asyncio.timeout` -> `asyncio.wait_for`; and on 3.10 `asyncio.TimeoutError` is not the builtin `TimeoutError`, so catch it by name. The ported code (`X | None`, walrus, `statistics.median`, `date.fromisoformat` on `YYYY-MM-DD`) runs on 3.10.
- **Type check and lint.** Replace `setattr(...)` and `**row.model_dump(include=...)` in the ported view code with explicit assignments and constructor calls. Rewrite comments that name HT's spec sections, runs or probes.
- **Dependencies.** None new. `httpx` is already a dependency of core and server; the search uses `difflib`.
- **Performance (measured).** models.dev: 6.78 MB of JSON, about 0.70 MB gzipped, 1.2 s to download, `json.loads` 0.13 s, 324 providers and 10,024 entries. The join of 314 models (729 entries) against prebuilt indexes takes 12 ms, and it runs only when a source changes. A reload on a normal day is one conditional GET. The search is 314 rows by two strings per call. The remaining cost per request is the `/api/available_models` logic, the same as the UI's own call: synchronous `requests` calls to Ollama on the event loop (up to 5 s for an unreachable custom host) and a disk walk for fine-tunes. This is existing behaviour and is accepted; a cache of a few seconds is a follow-up.
- **Two copies.** Until harness-tuner adopts these endpoints, it keeps its own copy of the join. A fix to the join goes to both, by hand, from the diff since the pinned commit.
- **Age of Kiln's own data.** The model list is as old as the app start, and provider notes and `models_dev_id` values are as old as the installed version. `sources.kiln_model_list` reports the first; nothing reloads either (out of scope, see the top of this doc).

## 12. Test plan

Tests sit beside the source. None patches a module: every dependency is passed in. **Fixtures.** Copy HT's `tests/fixtures/model_catalog/models_dev.json` and `kiln_config.json` to `services/model_info/test_data/`. Load the Kiln slice through Kiln's own `deserialize_config_data` and validate its `provider_list` as `KilnProviderInfo` (the facts file verified that all 7 models and 5 providers validate).

**`test_catalog_build.py`** (port of HT `tests/test_model_catalog.py:74-500`, models built as `KilnModel`): prices, limits and dates from the fixture; price on the exact pair; model facts follow the provider preference; loose date (no exact match, earliest date, a deprecated entry counts, a short key is not used, an exact match with no date falls back); median (across every models.dev provider, needs three paid prices, a provider counts once at its lowest price, 0 left out); `kiln_suggested_for` names; `models_dev_id` is used; a provider without it is not joined; a bad price and a bad limit are dropped; tags cleaned and capped; a long note is cut; no models.dev data gives null prices and Kiln's data; `parse_models_dev` on bad JSON and on a non-object. Not ported: the raw-parse cases (Kiln's deserializer owns them), the built-in map cases, the store cases.

**`test_models_dev.py`** (new). A `FakeClock` passed as `now`, and a `client_factory` that returns `httpx.AsyncClient(transport=httpx.MockTransport(handler))`; `wait_secs` and `fetch_timeout_secs` are hundredths of a second where a stall is tested. Cases: (1) first load gives `ok` data; the request has no `If-None-Match` and no header of ours; (2) `enabled=False`: `unavailable` / `turned off`, and a `client_factory` that raises is never called; (3) data younger than `max_age`: no request; (4) stale data: the call that finds it is answered at once with `stale` and the old data object, and starts one request with `If-None-Match`; after `await cache.settle()`, a 304 has kept the data object and moved `loaded_at`, and a 200 has replaced data and ETag, and the next call is `ok`; (5) each failure (non-200, timeout, transport error, over `max_bytes`, bad JSON, not an object) gives its reason and never raises; with no data the state is `unavailable`; with data it is `stale` and the data object is the old one; (6) no new request before `retry_after_empty` (no data) or `retry_after` (data), and one after it; (7) single flight: 20 concurrent `current()` calls make one request; (8) a stalled server, first load: `current()` returns after `wait_secs` with `unavailable` / `loading`, and after the handler is released the next call has the data; (8b) a stalled server, stale data: `current()` returns at once, without waiting `wait_secs` (the test sets `wait_secs` to 60 and a short test timeout), with `stale` / `refresh running` and the old data object; a second call during the refresh starts no second request; after the handler is released and `settle()`, the next call is `ok` with the new data; (9) `aclose()` cancels a running refresh, and a later `current()` starts none; a task left from another event loop is ignored.

**`test_view.py`** (port of HT `tests/test_gateway_model_info.py`, without the policy cases): the three statuses; `Offered` from a bad payload; ready entries only by default; `include_not_available`; deprecated left out by default; entry filters remove entries and then empty rows; a null value fails a filter; `reasoning_model` apart from thinking levels; the tag filter is ANY and a tag on an entry counts; price sort uses the median before the entries and a zero price never sorts; featured, price and newest with ties; paging and `total`; a pair the catalogue lacks; a model the catalogue lacks; server values win for an offered pair; details list every entry; provider counts and order; unconnected providers are listed and marked `not_connected`. New: search ranks 0 to 3, the typo pass sets `fuzzy_match`, an empty result, search order against an explicit `sort`, a search with no letter or digit; `featured` true and false; `include_notes`; unknown provider; case-insensitive details lookup; closest ids in the not-found text; no models.dev data gives Kiln's rows with null prices.

**`test_service.py`** (new): the catalogue is rebuilt when the models.dev data object changes and when the Kiln list changes, and not otherwise; `sources` for `remote_config` and `built_in`, with ages from the fake clock.

**`test_model_info_api.py`** (new): `FastAPI()` + `connect_custom_errors` + `connect_model_info_api(app, available_models=fake, models_dev=FakeSource())` + `TestClient`. Query parsing (repeated `tags`, booleans; `limit` 0 and 201 and 13 tags give 422); the 404 and 422 bodies of section 1.4; `sources` in all three answers; each route has `x-agent-policy` allow and no `x-mcp-policy` in `app.openapi()`.

**Edited test files.** `test_provider_api.py`: `available_models()` returns what the route returns. `test_remote_config.py`: the load time is set on success and not on failure. `test_config.py`: `skip_models_dev` reads `KILN_SKIP_MODELS_DEV`. `test_dev_server.py`: the dev environment does not set it.

**No-network guarantee.** Three layers: the route, service and view tests get fakes and make no HTTP call; the cache tests use a mock transport; and for any test that builds the real app, the root fixture turns the cache off. One test asserts the last layer: `make_app()` under the test suite has `app.state.models_dev_cache.enabled is False`.

## 13. Open items

To verify during implementation:

- **Legacy custom-model provider id.** `/api/available_models` lists legacy custom models under `provider_id=openai_compatible`, `provider_name=kiln_custom_registry`, with id `<provider>::<model>`. Kiln's run code treats such ids only under `kiln_custom_registry`. Model info would show `openai_compatible` for them. Check that a run config with the pair the endpoint shows does run; if it does not, fix the provider id in `available_models()` before the skill tells agents to trust `provider`.
- **Memory.** The size in memory of the slim models.dev form (estimate: a few MB).
- **Lint and types.** Whether `ty` and ruff reject HT's `setattr` and `**model_dump` forms (they are rewritten anyway, section 11).

This component has no owner decision of its own. The project's open items are in [architecture.md](../architecture.md) section 11, and the follow-ups (the web UI's `price.ts`, a cache for the availability check, a hint field for search, the models.dev terms of use, the hosted Assistant, harness-tuner adopting these endpoints) are in its section 8. The known limits are stated where they are designed: 6.3, section 7, section 10 and section 11.
