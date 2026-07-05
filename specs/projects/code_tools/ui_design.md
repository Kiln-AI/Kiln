---
status: complete
---

# UI Design: Code Tools

All UI lives in the Kiln desktop web UI (`kiln:app/web_ui`, SvelteKit + Tailwind + DaisyUI), following existing Tools-tab conventions. Component names reference real files verified on `scosman/evals_v2`. Behavior contracts live in [functional_spec.md](functional_spec.md); this doc covers structure and interaction.

## 1. Page inventory

| Page | Route | New/changed |
|---|---|---|
| Tools index | `tools/[project_id]` | Changed: code tools appear as rows in the existing table |
| Add Tools | `tools/[project_id]/add_tools` | Changed: Code Tool card in Suggested + Custom sections |
| Create Code Tool | `tools/[project_id]/add_tools/code_tool` | New — one route, two wizard steps |
| Code Tool detail | `tools/[project_id]/code_tools/[code_tool_id]` | New |

Breadcrumbs: `Optimize → Tools → Add Tools → New Code Tool` (create wizard) / `Optimize → Tools → <name>` (detail page). Both new pages set `agentInfo` (per-page copilot context) and fire `posthog.capture` on create, per convention.

## 2. Tools index

**No new section.** Code tools are rows in the existing tools table (`+page.svelte`, columns Name / Type / Description / Status): Name = display name, Type = "Code Tool" (extend the type-formatter mapping), Description = user-facing description, Status = "Ready" ("Archived" badge when archived; code tools have no connectivity state, and Ready beats blank). Row click → detail page. Archived rows follow the table's existing archived treatment (sorted last / hidden per current behavior).

## 3. Add Tools page

Two insertions in `add_tools/+page.svelte`:

1. **Suggested Tools carousel**: a "Code Tool" feature card — *"Write a Python function that runs as a tool, and can call other tools."* → `goto` the create route. Positioned 4th in the carousel, after "Kiln Task as Tool".
2. **Custom Tools section** (`KilnSection`): a "Code Tool" entry with the same copy, between Kiln Task as Tool and Remote MCP.

## 4. Create flow — one route, two steps

Single route hosting a two-step wizard. **Steps are history entries** (SvelteKit shallow routing / `pushState`), so browser Back returns to step 1 with state intact — never surprise data loss. There is no in-UI Back button; browser Back is the only step-navigation affordance. Nothing is persisted until Create on step 2 (confirmed); `warn_before_unload` guards the whole flow.

### Step 1 — Define

`AppPage` + `FormContainer` (submit = "Continue"), heavy create-task reuse:

- **Name** — display name (`FormElement`).
- **Tool Name** — function name, `tool_name_validator`, live-validated.
- **Description** — the model-facing `tool_description` ("Shown to the model — describe what it does and when to use it"). The user-facing `description` field is **P2** and omitted from this screen (functional spec §1.1) — if added later it lives on the detail page's edit dialog, not here.
- **Parameters** — the create-task `SchemaSection` experience (structured mode only — no plaintext toggle, tools are schema'd; empty properties allowed for zero-arg tools). The structured option radio label is overridden to "Structured Parameter List" (default elsewhere is "Structured JSON") via the `structured_label` prop. No output schema (MCP outputs are untyped in practice).

### Step 2 — Code & Test

Subtitle: *"Write a tool that invokes a Python function, optionally calling other tools."*

The code-eval page shape: **code left, right panel with tools + test**. Three equal-weight section headers (`text-xl font-bold`): **Code** (left column), **Tool Access** and **Test** (right column).

**Left — Code**: section header "Code", then a `FormElement` sub-label "Python Function" with an info tooltip (*Must include either \`def run(...)\` or \`async def run(...)\`.*). The sub-label spans the full column width. Editor is `code_editor.svelte` (CodeMirror 6, python). Pre-filled on first entry with a **typed placeholder generated from step 1's schema** (`code_tool_helpers.ts`, mirroring `code_eval_helpers.ts`):

```python
def run(job_ids: list[str], limit: int = 10) -> str:
    """<tool_description>"""
    # TODO: implement
    return "result"
```

- Type mapping: `string→str`, `integer→int`, `number→float`, `boolean→bool`, `array→list[<item>]`, `object→dict`; properties not in `required` get `| None = None`.
- If the user navigates back and edits the schema, **never clobber written code** — the placeholder only fills an editor that is empty or still exactly the generated text; otherwise show a subtle hint ("Schema changed — check `run()`'s parameters").
- "Examples" dialog (code-evals pattern): parallel-with-retries (threads + `tools`), async fan-out (`async_tools` + `gather`), filtering a noisy tool result with `json.loads`.
- Below the editor, collapsed **Advanced**: timeout seconds (default 60, min 1).

**Right panel, top — Tool Access**: section header "Tool Access", then the run-config tools picker (`$lib/ui/run_config_component/tools_selector.svelte` + settings, own label "Tools"), fed by `available_tools`, filtered per functional spec §4.1 (no skills; the CODE group included). Inline warning when two selected tools share a function name ("ambiguous — calls to `search` will fail"). Helper text: "The code can only call tools listed here."

- **Import-helper UX**: when a tool is selected and the code does not contain `from kiln import tools`, prepend to the top of the editor:

  ```python
  # Run tools with `tools.<function_name>(...)` or `await async_tools.<function_name>(...)`
  from kiln import tools, async_tools

  ```

  with `<function_name>` = the just-selected tool's real function name. One-shot (only when the import line is absent); never duplicated.

**Right panel, below — Test panel** (§6).

**Create** (primary action, bottom): POSTs the create endpoint; validation errors (syntax, size cap, missing `run`, duplicate function name) render in the `FormContainer` error banner with the server's message. If no successful test has run since the last edit, show the code-evals "Save Without Testing?" confirm. On success: `uncache_available_tools()`, go to the detail page.

## 5. Detail page (saved tool)

`AppPage` with `property_list` (type, function name, timeout, created), action buttons, and:

- **Code** — `code_editor.svelte` in `readonly` mode. **P2**: copy button on the code block (the `<Output>` component's copy affordance).
- **Tool Access** — read-only list of allowlisted tools (names + source), `tool_schema_viewer`-style.
- **Test panel** — same component as step 2, running against the saved tool's fields (v1, confirmed).
- **Edit** — `edit_dialog` for display name (+ user-facing description if the P2 field ships).
- **Clone** — action button → create flow pre-filled via page state (the kiln-task-tool clone pattern), landing on step 1 with a "copy of" function name prompt (uniqueness enforced at create).
- **Archive / Delete** — existing `edit_dialog` archive pattern + `delete_dialog`.

## 6. Test panel (shared component, create + detail)

RAG "Test Search Tool" shape + code-evals trust orchestration. Mirrors the code-evals test panel interaction pattern: inputs are edited in a **wide modal** (`Dialog width="wide"`), while the sidebar shows a **compact truncated preview** of the current values with an "Edit" affordance.

- **Inputs**: sidebar shows a compact card (`rounded-lg border`) with per-parameter truncated previews (`line-clamp-2`) and an "Edit" link. Clicking "Edit" opens a wide `Dialog` titled "Edit Test Input" containing the full form generated from `parameters_schema` via the existing run-input form elements (`run_input_form_element.svelte`). Zero-param tools show just Run (no input card or modal).
- **Warning line** (always visible): "Runs your code live against real tools — side effects included." (Security-related copy: ships behind a `# TODO` requiring human sign-off, per functional spec §7.)
- **Run** → POST test endpoint with current editor/tool state + params; spinner; cancellable.
- **Trust intercept**: `not_trusted` response → **stopgap**: the existing code-eval trust dialog pattern/endpoints verbatim (functional spec §5 — final trust UX is out of this spec's scope; replaced in the last implementation phase).
- **Results**, stacked:
  - **Output** — the exact string the model would receive (`Output` component: JSON pretty-print/collapse for free).
  - **Tool calls** — compact table from `tool_call_log`: function name, arguments (collapsed JSON), duration, error badge. Hidden when empty.
  - **Error** — `error_with_trace.svelte` (message + styled Python traceback). Validation 400s render in the same slot without a traceback.
  - Duration shown subtly ("1.4s").
  - **P2**: stdout/stderr collapsed sections (fields are already in the API response).

## 7. Run-config integration (zero new UI)

`tools_selector.svelte` and other `available_tools` consumers pick up the "Code Tools" group automatically. Trust-gate errors during real agent runs surface through existing tool-error rendering in traces.

## 8. Component inventory

**New**: create-flow page (2-step wizard shell), `code_tool_helpers.ts` (typed placeholder + examples codegen + import-helper), shared test-panel component, detail page, add-tools card entries, API client wrappers (typed via regenerated `api_schema.d.ts`).

**Reused as-is**: `AppPage`, `FormContainer`/`FormElement`, create-task `SchemaSection` (structured mode), `code_editor.svelte` (edit + readonly), `tools_selector.svelte`, `run_input_form_element`, `Output`, `error_with_trace`, `property_list`, `Dialog`/`edit_dialog`/`delete_dialog`, `Collapse`, `KilnSection`, `FeatureCarousel`, `tool_name_validator`, code-eval trust-dialog pattern (stopgap).

**Removed**: none (no existing cards were removed).
