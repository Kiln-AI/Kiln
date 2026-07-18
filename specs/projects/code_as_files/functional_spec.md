---
status: draft
---

# Functional Spec: Code as Files

Behavioral contract for the change described in [project_overview.md](project_overview.md). Applies to the **desktop app** (`app/desktop` + `app/web_ui`) and the core library (`libs/core/kiln_ai`). No migration (nothing shipped). Where this spec is silent, the `code_tools` and code-evals behavior is unchanged.

## 1. On-disk layout

### 1.1 Code tools

```
{project}/code_tools/{id} - {name}/
  ├── code_tool.kiln      # metadata + functional fields, EXCEPT code
  └── tool.py             # the Python source (module-level `run`)
```

- `tool.py` is a fixed name. It holds exactly the source the author wrote — no wrapping, no header, no rewriting. Byte-for-byte what runs and what tests import.
- `code_tool.kiln` no longer contains a `code` field. It carries everything else (`tool_function_name`, `tool_description`, `parameters_schema`, `timeout_seconds`, `tool_allowlist`, metadata).

### 1.2 Code judges

```
{task}/.../eval_configs/{id} - {name}/
  ├── eval_config.kiln    # EvalConfig; its CodeEvalProperties has no `code` field
  └── scorer.py           # the Python source (module-level `score`)
```

- `scorer.py` is a fixed name, beside `eval_config.kiln`. Only code-eval configs write it; other eval-config types (`LlmJudgeProperties`, etc.) are untouched and write no sibling file.

### 1.3 Invariants

- Exactly one code file per code artifact, at the fixed name, in the artifact's own folder.
- The file is written on save and read on load. It is never referenced by absolute path and never lives outside the artifact folder (the same containment guarantee attachments enforce).
- The `.kiln` file and its code file are a unit: a code artifact is only valid with both present.

## 2. Persistence semantics

### 2.1 Save

Saving a code artifact writes the code to its sibling file and omits it from the `.kiln` JSON:

- **Code tool**: `save_to_file()` writes `tool.py` into the artifact folder; `code` is absent from `code_tool.kiln`.
- **Code judge**: saving the parent `EvalConfig` writes `scorer.py` into the eval-config folder for a `CodeEvalProperties`; `code` is absent from the serialized `properties`.

The code file is written from the in-memory `code` string as-is (UTF-8). Saving is idempotent — re-saving an unchanged artifact yields byte-identical files.

### 2.2 Load

Loading reads the code back into the in-memory `code` string before validators run, so the existing validation trio (§4) runs against the loaded code exactly as before:

- The loader makes the artifact's source folder available to model validation (today it is not — see architecture §3), then the code field is populated from the sibling file.
- **Missing/unreadable code file** → load fails with a clear error naming the expected file (e.g. `code_tool.kiln at <path> is missing its tool.py`). This mirrors how a dangling attachment fails and how a broken artifact surfaces today; a code artifact without its code is not loadable.

### 2.3 Immutability, clone, archive, delete — unchanged in contract

- **Immutable functional content** still holds: `code` (now `tool.py`) is frozen post-create; changing it means **clone**. Clone reads the source's code file and writes a fresh one under the new artifact's folder.
- **Archive/unarchive**: metadata only; files untouched.
- **Delete**: removes the artifact folder, including its code file and any author-added test files in that folder (existing `delete()` `rmtree` behavior).
- **Edit** still touches only `name` / `description` / `is_archived`; none of these move or rewrite the code file.

### 2.4 Transient execution (test endpoints) — no file involved

The `test_code_tool` and `test_v2_eval` endpoints build an unsaved model from the request, execute, and persist nothing. Because they never call `save_to_file()`, they never write a code file — they execute the in-memory `code` string straight through the sandbox, exactly as today. This is the guarantee that makes the execution engine "untouched": it always receives an in-memory string, whatever the source.

## 3. Authoring & UI behavior

The authoring UX is unchanged; only the storage under it moves.

- **Create wizard** (code tool): same two-screen flow (define → code+test), same CodeMirror editor. On save, the editor's contents become `tool.py`. The transient test panel is unaffected (§2.4).
- **Detail page**: shows the code read from `tool.py` (read-only, as today), metadata edit, clone, archive.
- **Code-eval form**: same editor; on save the contents become `scorer.py`.
- **No test UI.** Kiln shows no test files, no "run tests" control, no test results (decision 4). The detail page **may** show a short, static "How to test this tool" snippet linking to the docs (§5) — presentation only, P2, no execution.

## 4. Validation — unchanged rules, new source

The save-time trio is unchanged in behavior; it just runs against the code loaded from / about to be written to the file:

- **Code tool** (`code_tool.py` validators): ≤ 64 KB UTF-8; `compile(...)` (syntax); AST scan for a module-level `run` (`def` or `async def`); plus the schema/allowlist validators.
- **Code judge** (`eval.py` `CodeEvalProperties.validate_code`): ≤ 64 KB UTF-8; `compile(...)`; AST scan for a module-level `score`.

A code artifact whose sibling file fails the trio is invalid at save (create) and at load (a corrupted/hand-edited file surfaces the same validator error).

## 5. Testability — the deliverable

This is the point of the project. After this change, an author (human or agent) working in a Python environment with `kiln_ai` installed can:

### 5.1 Code tools

1. `cd` into the tool's folder (or point `pytest` at it).
2. Write `test_tool.py` beside `tool.py`:

   ```python
   import json
   import tool  # the artifact's tool.py — imports cleanly now

   def test_happy_path(kiln_tools):
       kiln_tools.set("get_user", '{"id": 1234, "name": "Alice"}')     # static reply
       kiln_tools.set("list_jobs", lambda **kw: json.dumps(["a", "b"])) # or a callable
       out = tool.run(job_ids=["a", "b"])
       assert json.loads(out)["name"] == "Alice"
       assert kiln_tools.calls[0].name == "get_user"                   # call assertions

   def test_unknown_tool_raises(kiln_tools):
       from kiln.tools import ToolNotAllowed
       # a name that was never registered behaves like a non-allowlisted tool
       ...
   ```

3. Run `pytest`. It passes/fails like any Python test.

The enabling mechanism is a shipped **`kiln` test shim** (`pytest` plugin, §6): it installs the same synthetic `kiln` / `kiln.tools` / `kiln.async_tools` surface the sandbox installs, so `from kiln import tools` at the top of `tool.py` resolves during test collection, and the `kiln_tools` fixture lets the author stub each tool's reply and inspect calls.

### 5.2 Code judges

No shim needed. The author writes `test_scorer.py`:

```python
from scorer import score

def test_scores_exact_match():
    assert score(reference_data={"answer": "42"}, output="42") == 1.0
```

`score()`'s inputs are plain arguments; it depends only on stdlib + `kiln_ai`, both importable in a normal environment.

## 6. The `kiln` test shim — behavioral contract

A `pytest` plugin shipped with `kiln_ai` (auto-discovered; no per-artifact files written by Kiln).

- **Import fidelity**: presents the exact module surface the sandbox presents (`tools.<name>(**kwargs) -> str`, `async_tools.<name>` awaitable, `list_tools()`, and the identical exception classes `ToolNotAllowed` / `ToolTimeout` / `ToolCallError` with `.tool` / `.message` / `.raw`). A test that catches `kiln.tools.ToolCallError` catches the same behavior the runtime raises.
- **Install timing**: the modules are installed into `sys.modules` at plugin load, *before* test modules are imported — so a top-level `from kiln import tools` in `tool.py` resolves during collection. (A fixture alone is too late; this is why it's a plugin.)
- **`kiln_tools` fixture** (function-scoped, auto-reset between tests):
  - `kiln_tools.set(name, reply)` — register a reply for a tool function name. `reply` is a `str` (returned verbatim, matching the string-returns contract) or a callable `(**kwargs) -> str`.
  - `kiln_tools.set_error(name, exc)` — make a name raise a given `ToolNotAllowed` / `ToolTimeout` / `ToolCallError`.
  - Unregistered name → raises `ToolNotAllowed` (matches the runtime allowlist-miss).
  - `kiln_tools.calls` — ordered record of `{name, arguments}` for assertions.
  - `list_tools()` returns the registered tools' declarations (name + whatever the author supplies).
  - An `async` path (`async_tools`) backed by the same registry so `await async_tools.x()` works under `asyncio.gather`.

The plugin is a test-support surface only: it never spawns a subprocess, never calls a real tool, and is never loaded inside the sandbox (the sandbox installs its own real bridge).

## 7. Edge cases

- **Hand-edited `tool.py` after create**: out of the immutability contract, but if it happens, the next load runs the validator trio against the edited file — a syntax error or missing `run` fails the load with the normal validator message. (Note the model cache keys on the `.kiln` mtime, not the `.py` mtime — see architecture §3 risks.)
- **Zero-argument tool / empty schema**: unchanged; `tool.py` still defines `run()`.
- **Two code tools in different folders both named `tool.py`**: fine — different directories. A single `pytest` run spanning multiple tool folders can hit module-name collisions (`tool` imported from two places); the documented pattern is to test one tool folder at a time (or use `rootdir`/`importmode=importlib`). Called out in docs (§5), not solved by Kiln.
- **Packaged desktop app has no `pytest`**: expected. Testing is an authoring-environment activity (dev / agent with `kiln_ai` installed); the shipped desktop app runs tools, it doesn't test them. Consistent with decision 4 ("Kiln doesn't run tests").
- **`code` present in an old inline `.kiln` JSON**: not supported (no migration). Such a file predates this change and won't load; dev fixtures that inline `code` in JSON must be regenerated (architecture §8).

## 8. Out of scope

Same as [project_overview.md](project_overview.md): Kiln-managed tests (artifacts / run-tests endpoint / test UI), any execution-engine change, migration, and everything already out of scope for the `code_tools` project.
