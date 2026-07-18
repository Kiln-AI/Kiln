---
status: draft
---

# Architecture: Code as Files

Technical design for [functional_spec.md](functional_spec.md). Target: `Kiln-AI/kiln`, on top of the `code_tools` branch (`claude/code-tools-design-t4jqbq`). File paths verified against that branch. The change is deliberately narrow: **storage + a test shim**, with the execution engine and agent harness untouched.

## 1. Strategy

- Keep `code` a plain in-memory `str` on both models. Nothing that reads `code` at runtime (validators, `PythonCodeTool`, the sandbox worker, the code-eval adapter, the transient test endpoints) changes.
- Change only *where the string comes from and goes to* at the (de)serialization boundary: write it to a fixed-name sibling file on disk-save; read it back on load; omit it from the `.kiln` JSON. Keep it present in normal/API dumps.
- Add one small, symmetric base-model affordance — the source folder in the load context — because a validator cannot otherwise know where its file is (`basemodel.py:434` validates before `m.path` is set at line 439).
- Ship the `kiln` test shim as a `pytest` plugin so authored tests can import a tool and stub its tool calls.

## 2. File inventory

### Library — `libs/core/kiln_ai`

| File | Change |
|---|---|
| `datamodel/basemodel.py` | **One base change.** `load_from_file` adds the source folder to the validation context: `context={"loading_from_file": True, "source_dir": path.parent}` (line ~434). Symmetric with the save side, which already passes `dest_path=path.parent` (line 500). Other models ignore the new key. |
| `datamodel/code_tool.py` | Route `code` through `tool.py`. Add `TOOL_CODE_FILENAME = "tool.py"`. Add the before-validator (§3.1) and the model serializer (§3.2). `code: str` stays required; the validation trio (`validate_code`, lines 78–102) is unchanged. |
| `datamodel/eval.py` | Same for `CodeEvalProperties` with `SCORER_CODE_FILENAME = "scorer.py"`. Before-validator + model serializer (§3.3). `validate_code` (lines 209–237) unchanged. Handles the nested-in-`EvalConfig.properties` case (§3.3). |
| `sandbox/tools_api.py` | **Behavior-preserving extraction only** (§4): factor the synthetic-module *surface* (proxy attribute behavior, `list_tools`, and the `ToolNotAllowed`/`ToolTimeout`/`ToolCallError` definitions) into a shared, stdlib-only helper the shim also imports, so runtime and tests present one definition of `kiln.tools`. The sandbox's real bridge and `install_tools_modules` (line 199) keep identical behavior; the existing sandbox test suite must pass unchanged. (Alternative if we want the sandbox literally untouched: the shim reimplements the surface and a contract test asserts parity — noted in §9.) |
| `tool_testing/` | **New package.** The `pytest` plugin + fake bridge + `kiln_tools` fixture (§5). Registered as a `pytest11` entry point. Stdlib + `kiln_ai` only. |

**Unchanged (verified in scope):** `tools/code_tool.py` (`PythonCodeTool` reads `self.code_tool.code` in memory), `sandbox/worker.py`, `sandbox/spawn.py`, `sandbox/entrypoint.py`, `adapters/eval/v2_eval_code_eval.py`, `adapters/eval/sandbox_worker.py`. Execution always receives an in-memory string.

**Runtime never imports the sibling file (hard invariant — see functional spec §1.3).** The datamodel reads the file into `code` at load; the sandbox child gets the string via `Process(args=(code, …))` and `exec()`s it, exactly as `worker.py` does today. The sandbox must not add the artifact folder to `sys.path` and must not `import` the `.py` file or any sibling — preserving the stdlib-plus-Kiln-bundle environment and preventing stray folder files (author test files, `conftest.py`) from being importable/executable at runtime. `import`-based loading exists only in the external `pytest` harness (§5).

### Desktop — `app/desktop/studio_server`

| File | Change |
|---|---|
| `code_tool_api.py` | No functional change. Create still constructs the model and calls `save_to_file()` — which now also writes `tool.py`. GET still returns the full artifact including `code` (in memory, read from the file at load). Confirm no endpoint or serializer assumes `code` lives in the `.kiln` JSON. |
| eval-config save path | Untouched code, but saving a code-eval `EvalConfig` now writes `scorer.py` (via `EvalConfig.save_to_file()` → nested serializer, §3.3). Verify the create/save endpoint round-trips. Code-eval endpoint policies remain out of scope. |

### Web UI — `app/web_ui`

Minimal. The API response shape is unchanged (`code` still present), so the detail page and code-eval form need no data-flow change. Optional P2: a static "How to test this tool" snippet + docs link on the detail page (presentation only). Regenerate `api_schema.d.ts` only if any response model actually changes (it should not).

### Packaging / docs

- Ensure project export/zip and git-sync include the sibling `.py` files. Attachments already depend on all folder files being carried, so this should hold — add a regression test that an exported/synced project round-trips `tool.py` / `scorer.py`.
- Register the `pytest11` entry point in `libs/core/pyproject.toml`.
- Update `docs/code_tools_guide.md` (and the code-eval guide) with a "Testing your tool / judge" section (functional spec §5).

## 3. Persistence mechanism

### 3.1 Load — before-validator injects code from the file

`code` stays a required field. A `mode="before"` validator injects it from disk during load, so field validation and the trio run normally:

```python
# code_tool.py
@model_validator(mode="before")
@classmethod
def _read_code_file(cls, data, info):
    ctx = info.context or {}
    if ctx.get("loading_from_file") and isinstance(data, dict) and "code" not in data:
        src = ctx.get("source_dir")
        if src is None:
            raise ValueError("Cannot load CodeTool: source_dir missing from load context")
        code_path = Path(src) / TOOL_CODE_FILENAME
        try:
            data["code"] = code_path.read_text(encoding="utf-8")
        except OSError as e:
            raise ValueError(f"code_tool.kiln is missing its {TOOL_CODE_FILENAME}: {e}") from e
    return data
```

A missing/unreadable `tool.py` fails the load with a clear message (functional spec §2.2). `mode="before"` validators receive `info` (hence context); the injected `code` then flows through the existing `validate_code`.

### 3.2 Save / dump — model serializer writes the file, omits code from the `.kiln` JSON

`save_to_file()` already dumps with `context={"save_attachments": True, "dest_path": path.parent}` (basemodel.py:498–501). A wrap serializer uses that context to write the file and drop `code`; without it (normal/API dumps) it leaves `code` in place:

```python
@model_serializer(mode="wrap")
def _serialize(self, handler, info):
    data = handler(self)                      # default dict, honoring exclude={"path"} etc.
    ctx = info.context or {}
    if ctx.get("save_attachments") and ctx.get("dest_path"):
        dest = Path(ctx["dest_path"])
        (dest / TOOL_CODE_FILENAME).write_text(self.code, encoding="utf-8")
        data.pop("code", None)                # code lives in tool.py, not the .kiln
    return data
```

Result: the on-disk `.kiln` has no `code`; API responses and other dumps keep `code`. This inverts the attachment rule (attachments never inline content) intentionally — the API contract for code tools keeps returning `code` unchanged.

### 3.3 Code judges — the nested case

`CodeEvalProperties` is a `BaseModel` member of the `V2EvalConfigProperties` discriminated union (`eval.py:240`), stored in `EvalConfig.properties`. It is never saved on its own; it is serialized/validated as part of `EvalConfig`. Pydantic propagates the serialization/validation **context to nested models**, so the same before-validator and wrap serializer work when placed on `CodeEvalProperties`:

- On `EvalConfig.save_to_file()`, `dest_path` = the eval-config folder → the nested serializer writes `scorer.py` there and drops `code` from the serialized `properties`. The wrap serializer preserves `type` (needed by the discriminator), `reference_keys`, and `timeout_seconds`.
- On load, the base `source_dir` context reaches the nested before-validator, which reads `scorer.py`.

**Must verify** context actually reaches discriminated-union members in this Pydantic version (KilnAttachmentModel is precedent for nested context, but confirm for union members; test in Phase 2 first).

## 4. Shared `kiln.tools` surface

The shim must present the same surface user code expects (`tools.<name>()`, `async_tools.<name>`, `list_tools()`, and the three exception types with `.tool`/`.message`/`.raw`). To keep runtime and tests from drifting, extract the surface definition from `sandbox/tools_api.py` into a stdlib-only helper that:

- builds the `kiln` / `kiln.tools` / `kiln.async_tools` module objects given a **bridge** (an object with `.call(name, kwargs) -> str`, `.list_tools()`, and the exception classes), and
- defines the exception classes once.

The sandbox injects its real IPC bridge (unchanged behavior); the shim injects a fake, registry-backed bridge (§5). This is a mechanical extraction guarded by the existing sandbox suite — no execution behavior changes.

## 5. The test shim — `tool_testing/`

A `pytest` plugin (auto-discovered via `pytest11`). Key mechanics:

- **Install at plugin load** (a `pytest_configure` hook, before test modules import): put the shim's `kiln` / `kiln.tools` / `kiln.async_tools` into `sys.modules`, backed by a module-global fake bridge. This makes a top-level `from kiln import tools` in `tool.py` resolve during collection. (A fixture alone runs too late.)
- **`kiln_tools` fixture** (function scope): resets the fake bridge's registry and call log per test; exposes `set(name, reply)`, `set_error(name, exc)`, and `calls`. `reply` is a `str` (returned verbatim) or `(**kwargs) -> str`. Unregistered name → `ToolNotAllowed`. Backs both the sync `tools` and async `async_tools` proxies from one registry.
- **Never executes real tools or subprocesses.** Pure in-process fake.

Because the modules are process-globally installed, `tool.py`'s `run()` transparently calls the fake; the fixture only manages per-test state. Judges use no shim — they import `scorer.py` and call `score(**inputs)` directly.

## 6. Control flow (save/load round-trip)

```
create/clone → CodeTool(code="…") in memory → save_to_file()
    model_dump_json(context={save_attachments, dest_path})
        wrap serializer: write dest/tool.py, drop `code` → code_tool.kiln (no code)

load_from_file(path)
    model_validate(json, context={loading_from_file, source_dir=path.parent})
        before-validator: read source_dir/tool.py → data["code"]
        validate_code trio runs on the loaded string
    m.path = path
```

Same shape for `EvalConfig` → nested `CodeEvalProperties` → `scorer.py`.

## 7. Testing strategy

1. **Datamodel round-trip (code tool)** (`test_code_tool.py`): save writes `tool.py`; `code_tool.kiln` contains no `code` key; load reconstructs `code`; validators run on the file content; missing `tool.py` → load error; clone writes a fresh `tool.py`; delete removes the folder. API-shaped `model_dump()` still includes `code`.
2. **Datamodel round-trip (code judge)** (`test_eval.py`): `EvalConfig` with `CodeEvalProperties` writes `scorer.py`; `properties` in `eval_config.kiln` omits `code` but keeps `type`/`reference_keys`/`timeout_seconds`; load reconstructs; nested-context propagation asserted explicitly.
3. **Serializer contexts**: disk save (with context) omits code + writes file; plain `model_dump`/API dump keeps code and writes nothing.
4. **Test shim** (`tool_testing` tests): plugin installs modules; `from kiln import tools` importable at collection time; `kiln_tools.set` static + callable; `set_error`; unknown name → `ToolNotAllowed`; `calls` recorded; `async_tools` under `asyncio.gather`; end-to-end importing a sample `tool.py` that calls `tools.x()`.
5. **Regression**: full existing `code_tools` + code-eval suites pass. Fixtures/tests that hand-write inline `code` in `.kiln` JSON, or construct-and-save then assert JSON contents, are regenerated to the file-based layout.
6. **Sandbox suite unchanged** after the §4 extraction (behavior-preserving).
7. **Packaging**: export/zip and git-sync round-trip a project containing `tool.py` and `scorer.py`.

## 8. Migration

None — nothing shipped. Consequence to handle *within this branch*: any `.kiln` fixtures or tests that inline `code` in JSON stop loading and must be regenerated to write sibling files (Phase 4). This is a test/fixture cost, not a user migration.

## 9. Risks / non-obvious constraints

- **Nested context to union members** (§3.3) — the one mechanism that isn't already proven by attachments; validate it in Phase 2 before building on it.
- **Base-model context key is shared** — `source_dir` reaches every model's validation; harmless (only code models read it), but keep the key name unambiguous and covered by a test that other models load unaffected.
- **Model cache keys on the `.kiln` mtime, not the `.py`** (`basemodel.py:426/456`) — a hand-edited `tool.py` won't invalidate a cached readonly model. Acceptable: code is immutable by contract; documented (functional spec §7).
- **`sandbox/tools_api.py` extraction** touches sandbox-adjacent code; if we'd rather leave the sandbox literally untouched, the shim reimplements the surface and a contract test asserts parity (§4 alternative). Recommend the extraction (one source of truth) with the existing suite as the guardrail — flag for scosman.
- **pytest module-name collisions** across tool folders — documented authoring guidance (one folder at a time / `importmode=importlib`), not a Kiln mechanism.
- **Export/git-sync must carry the `.py` files** — real files are strictly friendlier to git than escaped JSON, but add the round-trip test so it can't regress.
