---
status: complete
---

# Code as Files — Project Overview

Move the user-authored Python in **code tools** and **code judges** out of the `.kiln` JSON and into real, importable `.py` files stored beside the artifact. Ship an importable `kiln` test shim so a tool that calls other tools can be unit-tested outside the sandbox. The goal is a single, concrete capability: **an author (human or, per the roadmap, a tool-writing agent) can write and run standard `pytest` tests against a code tool or code judge.**

**Target repo:** `Kiln-AI/kiln` (library `libs/core/kiln_ai`, desktop server `app/desktop/studio_server`, web UI `app/web_ui`). This is a change to the not-yet-shipped code-tools + code-evals design — **no backwards compatibility or migration** is required.

## The design error we're fixing

Both features today store Python as an inline `str` in the artifact JSON:

- **Code tools** — `CodeTool.code` (`libs/core/kiln_ai/datamodel/code_tool.py:51`), serialized into `code_tool.kiln`.
- **Code judges** — `CodeEvalProperties.code` (`libs/core/kiln_ai/datamodel/eval.py:205`), serialized into `eval_config.kiln`.

A Python string trapped in JSON is not discoverable by `pytest`, not importable, and gets no editor/LSP/lint/type-check support. That makes the code effectively untestable with standard tooling — which directly undercuts the code-tools roadmap, where a **tool-writing agent authors these via the API** (project_overview of `code_tools`, decision 11). Agents write correct code by writing and running tests; they can't do that against a JSON string.

This reverses two locked decisions from the `code_tools` project that were premature:

- **Decision 8** ("code stored inline in the `.kiln` JSON — self-contained, diffable"). Kiln artifacts are already *folders* (`{id} - {name}/`), and attachments already colocate sibling files, so "self-contained" lives at the folder level, not the file level. And a real `.py` diffs *better* in git than an escaped-JSON string. The stated benefits survive the split; the testability cost does not.
- **Decision 10 / 3.x** ("no companion Python test file in v1"). We're not adding Kiln-managed test artifacts — but we are making tests *possible*, which decision 10 foreclosed.

## Decisions (locked, scosman 2026-07-18)

1. **Storage: fixed-name convention file, not the attachment model.** Code persists to a fixed, importable filename beside the `.kiln`:
   - Code tool → `tool.py` (so tests do `from tool import run`).
   - Code judge → `scorer.py` (so tests do `from scorer import score`).
   `KilnAttachmentModel` is rejected for this: it names files `{uuid}.py` (`basemodel.py:233`), which forces `importlib` path-loading instead of a clean `from tool import run`. We reuse the attachment *serialization-context pattern* (`save_attachments` / `dest_path`), not the attachment model itself.
2. **In-memory API is unchanged.** `code` stays a `str` on the model in memory (read from the sibling file on load, written to it on save). Validators, the execution engine, and the transient test endpoints see the same `str` they see today — the change is storage + authoring, not runtime.
3. **Scope: both code tools and code judges**, treated symmetrically, so the two features don't diverge.
4. **Testing is "code-as-file only."** Kiln makes the code a real importable file and ships an importable **`kiln` test shim** (a `pytest` plugin) so `from kiln import tools` resolves in tests and authors stub tool responses. Kiln does **not** store, display, or run tests — no test artifacts, no run-tests endpoint, no test UI. The test loop lives in a normal Python environment with `kiln_ai` installed.
5. **The execution engine is untouched.** The sandbox worker, IPC/nesting bridge, timeout, semaphore, and trust gate all take an in-memory code string regardless of where it came from. This change must not modify `libs/core/kiln_ai/sandbox/*` execution behavior or `adapters/eval/sandbox_worker.py`. The sandbox reads the code as a string and `exec()`s it — it **never** imports the sibling file or puts the artifact folder on `sys.path` (hard invariant; functional spec §1.3).
6. **One `kiln.tools` surface, shared by runtime and tests.** The synthetic-module surface (proxy behavior, `list_tools`, and the exception classes) is factored out of `sandbox/tools_api.py` into a stdlib-only helper that both the sandbox bridge and the test shim import — a behavior-preserving extraction guarded by the existing sandbox suite passing unchanged. This keeps runtime and test fidelity from drifting; it is not an execution-behavior change.

## Why the `kiln` test shim is load-bearing

Moving code to a file is necessary but **not sufficient**. A code tool's body does `from kiln import tools`, and that module only exists synthetically *inside the sandbox child* (`libs/core/kiln_ai/sandbox/tools_api.py:199`); there is deliberately no real `kiln` package. So the moment a test does `import tool`, it hits `from kiln import tools` → `ImportError`. Any tool that calls other tools is untestable until `kiln.tools` is importable and mockable outside the sandbox. Shipping that shim is the difference between "the code is a file" and "the code is testable."

Code judges need no shim: `score()` receives its inputs as plain arguments (reference data, model output) and depends only on stdlib + `kiln_ai`, so `from scorer import score; score(**inputs)` works directly once the code is a file.

## Out of scope

- Kiln-managed tests: test artifacts, a run-tests endpoint, test UI, cloning that carries tests (this is "code-as-file only", decision 4).
- Any change to sandbox execution behavior, nesting, trust, or the agent harness (decision 5).
- Backwards compatibility / migration of inline-code `.kiln` files (nothing has shipped).
- Everything already out of scope in the `code_tools` project (tool-writing agent, server-side execution, dependency management, secrets, typing stubs, etc.).
