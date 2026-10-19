# Code conventions: universal rules

These rules apply to every line a change adds or modifies, in Python and in TS/Svelte. Existing code that breaks them is grandfathered (see H). Rules tagged `(gate: <rule-id>)` are checked by `conventions_gate.py`; the rest are checked by you and by review.

Area-specific facts (dependency direction, entry points, where things go) live in the area references. This file holds only what is true in every area.

## A. Comments

Comments are rare in well-written code: names, types and structure carry the meaning. Write each one for someone opening the file cold a year from now, not for the reviewer of this change. Before writing a comment, try a better name or extracting a function. Anything you want the reviewer to know goes in your end-of-task summary or the PR description. Review-bot findings about comments, including ones labelled nitpick, are required fixes.

### A1. A comment must make sense to someone who never saw the diff `(gate: history-comment)`

Don't narrate history or change ("no longer", "used to", "previously", "switched to", "bumped from", "vestigial", "after the refactor"), and don't cite planning docs ("Phase N", "functional spec §x", "(P2)"). History goes in the commit message or PR description.

```python
# ❌
# The web client is no longer an EventSource, so this stays a GET (functional spec 5.2).
# ✅
# The eval page reads this stream with fetch() and a GET; a POST would break it.
```

On-disk back-compat is a durable fact, not history. State the data shape, not the story:

```python
# ❌
# Previously we stored rating values as a dict of floats.
# ✅
# Older task run files store ratings as a dict of floats; upgrade them on load.
```

### A2. Don't restate the code

No comments that narrate the next line, no section banners over obvious blocks, no docstrings that only repeat the name. Public SDK docstrings and published API route docstrings are the exception: they are docs for external readers, so write them well.

```python
# ❌
# Save any unsaved secrets first
self._save_secrets()
# Call the parent save_to_file method
super().save_to_file()

def strict_mode() -> bool:
    """Get the current strict mode setting."""
# ✅
self._save_secrets()
super().save_to_file()
```

### A3. Comments explain a non-obvious *why*, in 1–3 lines

Comment only when a careful reader would otherwise be confused or likely to break something: a fact about the outside world that shaped the code, a constraint the code can't express (ordering, units, an invariant enforced elsewhere), or a link to the upstream bug a workaround exists for. Never record or justify a decision ("we chose httpx because…", "kept simple on purpose"); decisions go in specs, commit messages or the PR. Never address the reviewer or defend the code against an imagined objection. If a guard needs a paragraph, it needs a better name or a helper.

```python
# ❌ (a 12-line essay above one `if`, defending it against a reviewer)
# ✅
# Provider X rejects the first request after a cold start; one retry is required.
```

Docstrings describe the contract (purpose, inputs, outputs, errors) for a first-time caller. No history, no rationale.

## B. Startup and entry points

### B4. Each runtime has one composition root

A process (app, server, worker, CLI, script) starts by calling one bootstrap function. That function owns process-wide setup: logging, error reporting, certs, library config, the model list. The area reference lists the entry points.

```python
# ❌ setup spread across import time, the app factory and lifespan
setup_certs()                      # at import of the entry module
def make_app():
    setup_litellm_logging()        # in the factory
    refresh_model_list_background()
# ✅
def main() -> None:
    bootstrap_process()            # certs, logging, litellm callbacks: once
    uvicorn.run(make_app(), ...)
```

### B5. Modules do no work at import time `(gate: module-level-call, module-level-construct, module-level-subscribe; WARN)`

No I/O, network, env or config reads, threads, client creation, registration, or changes to stdlib or third-party globals at module top level. Top level only defines things.

```python
# ❌
mimetypes.add_type("text/css", ".css")
csv.field_size_limit(100 * 1024 * 1024)
app = make_app()
# ✅
def connect_webhost(app: FastAPI) -> None:
    mimetypes.add_type("text/css", ".css")
```

```ts
// ❌ (store module)
ui_state.subscribe((state) => load_current_task(state))
// ✅
export function init_app_stores(): () => void {
  return ui_state.subscribe((state) => load_current_task(state))
}
```

### B6. App factories are pure

`make_app()` wires routes and middleware and returns. Long-lived resources (registries, clients, background tasks) are created at startup (FastAPI `lifespan`) and held by the app (`app.state`), not by modules.

```python
# ❌
job_registry = JobRegistry()          # module singleton, built at import
# ✅
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.job_registry = JobRegistry()
    yield
    await app.state.job_registry.shutdown()
```

## C. State and globals

### C7. No new module-level mutable state `(gate: global-stmt)`

No `global`, no module-level dict, list or set that gets mutated, no ClassVar registries. App-scoped objects are created at startup and passed in or injected.

```python
# ❌
_batch_jobs: dict[str, BatchJob] = {}
def cache_committer(name: str) -> None:
    global _cached_committer_name
    _cached_committer_name = name
# ✅
class BatchJobStore: ...
def connect_data_gen_api(app: FastAPI, jobs: BatchJobStore) -> None: ...
```

### C8. If a test has to reset it or patch it, it's in the wrong place

Don't add `reset()` hooks to production code for tests. Pass the dependency in instead.

```python
# ❌
class GitSyncRegistry:
    _managers: ClassVar[dict[str, Manager]] = {}
    @classmethod
    def reset(cls) -> None:  # used by tests
        cls._managers.clear()
# ✅
registry = GitSyncRegistry()          # created in lifespan, passed to handlers
```

### C9. No `asyncio.Lock`, `Semaphore` or `Event` in a module or process singleton

They bind to the first event loop that uses them. Create them per owner, inside the loop that uses them.

```python
# ❌
update_run_lock = asyncio.Lock()
# ✅
class RunStore:
    def __init__(self) -> None:
        self._locks: dict[Path, asyncio.Lock] = {}
```

### C10. A cache needs an owner, a bound, and an invalidation path

Never keep permission or trust decisions in a global.

```python
# ❌
finetune_cache: dict[str, Finetune] = {}     # unbounded, never invalidated
_trusted_projects: set[str] = set()          # security policy as module state
# ✅
@dataclass
class FinetuneCache:
    max_entries: int = 256
    def invalidate(self, finetune_id: str) -> None: ...
```

## D. Config

### D11. Read config once at the edge and pass values down `(gate, where enabled: core-config-shared)`

Read config in the entry point, route handler or dependency, then pass values as arguments. Don't read the global config deep in the call stack.

```python
# ❌ (inside an adapter)
api_key = Config.shared().open_ai_api_key
# ✅
def litellm_config(provider: str, credentials: ProviderCredentials) -> LiteLlmConfig: ...
# in the handler:
credentials = ProviderCredentials.from_config(config)
```

### D12. Parse config values with real parsers `(gate: bool-env)`

`bool("false")` is `True`. Use an explicit parser.

```python
# ❌
autosave = bool(os.getenv("KILN_AUTOSAVE_RUNS"))
# ✅
autosave = parse_bool(os.getenv("KILN_AUTOSAVE_RUNS"), default=False)
```

### D13. Read env vars only in the config module and the entry points `(gate: env-access)`

Never configure a library by writing `os.environ`. The gate's config lists the allowed paths.

```python
# ❌ (in a route module)
base_url = os.environ.get("KILN_SERVER_BASE_URL", "https://api.kiln.tech")
with temporary_env("OPENAI_API_KEY", "fake-api-key"): ...
# ✅
base_url = settings.kiln_server_base_url        # read once by the config module
VectorStoreIndex(..., embed_model=MockEmbedding(embed_dim=8))
```

### D14. Pydantic `default_factory` and validators are pure

No config, env, filesystem or network inside them.

```python
# ❌
created_by: str = Field(default_factory=lambda: Config.shared().user_id)
@model_validator(mode="after")
def upgrade(self):  # loads child files from disk
# ✅
created_by: str          # the caller passes the user id
# migrations run in an explicit load hook or a migration command
```

### D15. Config picks the implementation; code doesn't second-guess it by environment

Which implementation runs (a storage backend, a client, a provider) is chosen by config or env vars at deploy time. Code reads the setting and builds what it names. Don't branch on the environment name (`env == "prod"`, "staging", "development") to pick, require or forbid an implementation, and don't add startup guards that override the deploy config. Environment-specific choices live in the deploy config.

```python
# ❌
if settings.env not in ("test", "development") and settings.chat_storage == "inmemory":
    raise ValueError(...)
# ✅
storage = build_chat_storage(settings.chat_storage)  # the deploy config picks "gcs" or "inmemory"
```

## E. Modules and layering

### E16. Thin edges

Route handlers and pages parse input, call one service or flow function, and map the result. Multi-step logic goes in a service module (Python) or a `.ts` module (web) with unit tests. As a guide, a handler over ~50 lines, or one calling several services or endpoints, should be split. That number is a prompt to stop and think, not a hard limit.

```python
# ❌ a 300-line handler that validates, builds three models, calls a remote API and persists
# ✅
@app.post("/api/specs")
async def create_spec(request: CreateSpecRequest) -> SpecResponse:
    try:
        spec = await spec_creation.create_spec(request.to_input())
    except SpecInputError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return SpecResponse.from_spec(spec)
```

### E17. Services don't know about HTTP, and routers don't import each other

Service and util code doesn't import router modules and doesn't raise `HTTPException`. Routers don't import each other or each other's `_private` names.

```python
# ❌
from .data_gen_api import _resolve_task_runtime_prompt
# in a utils module:
raise HTTPException(status_code=404, detail="Eval not found")
# ✅
from .services.prompts import resolve_task_runtime_prompt
raise EvalNotFound(eval_id)            # the router maps it to 404
```

### E18. Respect the dependency direction of the area `(gate, where a path rule exists: lib-imports-routes)`

Each area reference states its direction. Shared code never imports from code that depends on it.

```ts
// ❌ (in lib/ui)
import Rating from "../../routes/(app)/run/rating.svelte"
// ✅ move the shared component into lib/ and import it from there
import Rating from "$lib/ui/rating.svelte"
```

### E19. No catch-all modules

Put a function in the module of the domain it belongs to, not in `utils`, `helpers`, `misc` or a "stores" file that holds display helpers.

```ts
// ❌ a "stores" module that is mostly model_name(), vector_store_name(), prompt_name_from_id()
// ✅ a model_display module for model_name() and provider_name_from_id()
```

### E20. Test helpers live in test files or test-support modules

Never in production packages, where they ship and get imported by accident.

```python
# ❌ helpers.py in a production package, importing unittest.mock and holding patch targets
# ✅ conftest.py, or a test-support module the build excludes
```

### E21. Prefer one shared helper or table over near-copies

A "keep in sync" comment means the code should be extracted.

```python
# ❌ fifteen connect_<provider>() functions differing only in URL and header
# ✅
PROVIDER_CHECKS = {"openai": KeyCheck(url=..., header=...), ...}
async def validate_key(provider: str, key: str) -> KeyCheckResult: ...
```

## F. Library vs. application

### F22. Library code doesn't change the global state of the process hosting it

That includes litellm settings, logging handlers or levels, `csv`, `mimetypes`, `os.environ`, `sys.modules`, `atexit` and signal handlers. If host-level setup is needed, the library exposes a `setup_*()` that adds to existing state rather than replacing it, and the entry point calls it.

```python
# ❌ (library)
litellm.callbacks = [CustomLiteLLMLogger()]
atexit.register(_shutdown_executor)          # at import
# ✅ (library exposes, entry point calls)
def setup_litellm_logging() -> None:
    litellm.callbacks.append(CustomLiteLLMLogger())
```

## G. Async and I/O

### G23. No blocking I/O inside `async def`; every outbound call has a timeout

Create clients once per process, not per call.

```python
# ❌
async def connect_openai(key: str):
    response = requests.get(url, headers=headers)        # blocks the loop, no timeout
# ✅
async def connect_openai(client: httpx.AsyncClient, key: str):
    response = await client.get(url, headers=headers, timeout=10)
```

## H. Grandfathering

### H24. New code follows these rules even when the code around it doesn't

Don't copy a pattern from nearby code that breaks a rule. Don't rewrite neighbouring code to comply either, unless the change is already touching it. If a rule can't be followed without a refactor, follow the local pattern and say so in the end-of-task summary. When that leaves a gate FAIL, don't allowlist it: list it in the summary and the PR description with the rule id, `path:line`, and the refactor it waits on. The allowlist is only for hits that aren't violations.

```python
# ❌ adding a 75th `Config.shared()` read to a handler file because the other 74 do it,
#    without saying so
# ✅ adding it, and writing in the summary: "Read Config.shared() in the new handler to
#    match the rest of the file; injecting config there is a separate refactor."
#    If that line also FAILs the gate, report it the same way
#    ("<rule-id> at path:line, waits on config injection"), don't allowlist it.
```
