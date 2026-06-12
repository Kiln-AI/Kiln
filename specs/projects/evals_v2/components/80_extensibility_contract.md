---
status: complete
approved: true
alignment_refs: [A2.4, A2.10, A2.11, B.12, E.36]
opens: []
summary: V2.0 extensibility stance — closed catalog + code_eval escape hatch; architectural seams for future plugins; how a new built-in type plugs in; judge template extensibility.
---

# Extensibility Contract

**Author:** sub-agent dispatched 2026-06-03 for Stage 4 gap-fill
**Status:** complete

## TL;DR

- V2.0 ships a **closed catalog** of 8 `V2EvalType` values. Adding a new built-in EvalConfigType requires a PR to Kiln. No runtime plugin discovery, no setuptools entry-point registration, no plugin marketplace.
- **`code_eval` is the per-project escape hatch** for anything the closed catalog does not cover (B.12). User-authored Python scorers handle the long tail of custom signal extraction, project-specific logic, and novel scoring.
- The architecture **does not foreclose** a future plugin model. Four seams (enum extension, properties union, adapter map, builder UI discovery) are identified and documented. Opening them is additive.
- **Judge prompt templates** are user-extensible today: every `llm_judge` EvalConfig carries its own Jinja2 `prompt_template`. First-party RAG templates (`components/29`) ship as pre-authored starting points, not a closed set.
- **Filter primitives** (extraction via `extract()` / `value_expression`) are internal-only for V2.0. The `extract()` helper is a library function, not an extension point; users cannot register custom extraction functions.
- This file **extends** `components/20`'s section 5 (extensibility seam) into the full contract. `components/20` defines the seams; this file documents what is stable, what is internal, and the conditions under which the seams would open.

---

## 1. V2.0 stance: closed catalog + `code_eval` escape hatch (E.36)

### 1.1 What "closed" means

The `V2EvalType` enum and `V2EvalConfigProperties` discriminated union are **hardcoded in Kiln source**. The only way to add a new EvalConfigType is to modify those definitions in a PR to Kiln's repository. There is:

- No runtime discovery of third-party type values.
- No setuptools entry-point registration (contrast: Inspect AI's 14-type registry, `reports/competitive_inspect_ai.md:330-348`).
- No plugin package format.
- No plugin marketplace or discovery UX.

### 1.2 Why closed for V2.0

Three constraints drive this:

1. **A0.4 (local-first; PyInstaller bundle stays clean).** Kiln's primary distribution is the PyInstaller-bundled binary. The bundle cannot `pip install` at runtime. A plugin model based on setuptools entry points (Inspect's approach) would only work for pip-installed Kiln, creating a two-tier ecosystem where bundled-app users cannot access community plugins. This is incompatible with Kiln's positioning.

2. **Builder UX requires a known catalog.** G.1/G.3 lock an exhaustive per-type renderer registry and a type-picker in the create UI. Both need the full type catalog at build time. Runtime-discovered types cannot be surfaced cleanly in the create flow or the view surfaces without a "plugin-provided fallback" renderer that degrades the experience.

3. **Quality and security consistency.** Every V2.0 type has test coverage, documentation, and builder UI integration. Third-party plugins cannot be held to the same bar without a review/certification process that does not exist.

### 1.3 `code_eval` covers the long tail (B.12)

Anything a third-party plugin could do -- custom signal extraction, project-specific logic, domain-knowledge scoring, novel statistical checks -- can be written as user Python inside `code_eval`. The user authors a scorer function that receives the eval inputs (output, trace, reference data) and returns a score dict.

**Limitation accepted:** `code_eval` is per-project. The code lives in the EvalConfig's `properties.code` field as an inline string. There is no built-in mechanism to share a scorer across projects. If users want to share, they share the code via copy-paste, an internal repo, or a shared library importable from the project's Python environment.

**Why this is sufficient for V2.0:** The competitive landscape confirms that most tools rely on inline code for custom scorers, not a plugin ecosystem (`reports/competitive_synthesis.md:115-129`). Braintrust, LangSmith, Langfuse, Weave, DeepEval, Promptfoo, and the OpenAI platform all use function/class-based inline scorers with no third-party plugin registry. Only Inspect AI has a pip-installable plugin model, and even there, the setuptools entry-point pattern is used primarily by the Inspect team itself, not a thriving third-party ecosystem.

---

## 2. Architectural seams for future plugins (E.36, A2.11)

The V2.0 architecture does not foreclose a future plugin model. The design deliberately preserves four seams that could be opened in a future version. This section documents each seam, what opening it would require, and what currently keeps it closed.

### 2.1 Seam: `V2EvalType` enum extension

**Current state:** `V2EvalType` is a `str, Enum` with 8 hardcoded values. Adding a value requires modifying the enum in source.

**Future plugin path:** A future plugin system would extend the enum with namespace-aware values (e.g., `"mypackage/my_scorer"`) to prevent collisions with built-in types. Two implementation options:

- **Relaxed parsing:** Change the `V2EvalConfigProperties` union's discriminator to accept unknown string values and route them to a plugin lookup. Unknown values that match no registered plugin raise at dispatch time, not parse time.
- **Dynamic enum registration:** At startup, iterate registered entry points and add their type values to `V2EvalType` before any EvalConfig parsing occurs.

**What keeps it closed:** PyInstaller distribution (no pip install at runtime); no startup-time entry-point scanning infrastructure; exhaustive enum matching in both backend (`_V2_ADAPTER_MAP`) and frontend (TypeScript `never` guard) would need fallback paths.

### 2.2 Seam: `V2EvalConfigProperties` union extension

**Current state:** `V2EvalConfigProperties` is an `Annotated[Union[...], Discriminator("type")]` with one properties class per built-in type. New properties classes require source modification.

**Future plugin path:** Plugin packages export a Pydantic `BaseModel` subclass with `type: Literal["mypackage/my_scorer"]`. At startup, the union is widened to include plugin-provided properties classes. Pydantic v2's `Annotated[Union[...], Discriminator]` supports dynamic union construction.

**What keeps it closed:** Same as 2.1. Additionally, EvalConfig files on disk containing a plugin-provided type would fail to parse on a Kiln installation that lacks the plugin, which conflicts with Kiln's file-sharing model (projects shared between users must parse cleanly). A "graceful degradation" story (load the EvalConfig but mark it as unrunnable) would need design work.

### 2.3 Seam: adapter map extension

**Current state:** `_V2_ADAPTER_MAP` (`components/20`, section 2.2) is a plain `dict[V2EvalType, type[BaseEval]]`. Dispatch is a dict lookup + exhaustive match assertion.

**Future plugin path:** Entry-point discovery at startup adds entries to the map. The dispatch function falls through from the built-in map to the plugin map. No change to the dispatch signature (`eval_adapter_from_type(eval_config: EvalConfig) -> type[BaseEval]`, per A2.11).

**What keeps it closed:** No entry-point scanning code; no plugin map; exhaustive match assertion would need to become a graceful "unknown type" handler.

### 2.4 Seam: builder UI discovery

**Current state:** G.3's per-type module registry (`{ label, icon, createForm, resultRenderer, requiresTrust }`) is exhaustive over `V2EvalType` at compile time (TypeScript exhaustiveness guard). A type with no registered module is a build error.

**Future plugin path:** A "plugin-provided" fallback renderer/form for types not known at compile time. The fallback would render a generic JSON editor for the properties class and a generic result display. This is the weakest seam -- the UX for plugin-provided types would be significantly worse than for built-in types.

**What keeps it closed:** No generic renderer exists; the TypeScript exhaustiveness guard would need a `default` fallback; the type-picker in the create flow would need a "Custom / Plugin" section listing runtime-discovered types.

### 2.5 When to open these seams

E.36 identifies the trigger: **demonstrated demand for cross-project scorer sharing.** If V2.x usage data shows that users are copy-pasting `code_eval` scorers across projects (the same scoring logic appearing in many projects), that validates the need for a shareable, installable scorer package. At that point:

- Target the **pip-installed Kiln distribution** (developers, CI environments) where `pip install kiln-my-scorer` is natural. The PyInstaller bundle would not gain plugin support unless a fetch-and-load mechanism is built (significant work, not currently planned).
- Adopt the Inspect-style setuptools entry-point pattern (proven, Python-ecosystem-native).
- Build the "graceful degradation" path for EvalConfig files referencing absent plugins.
- Build the generic fallback renderer for the builder UI.

---

## 3. How a new built-in type plugs in (A2.4, A2.11, A2.10)

This section documents the concrete steps to add a new built-in EvalConfigType (e.g., `json_schema` post-V2). This is the same process used by every V2.0 type. The architecture is uniform; no special "extensibility API" is needed.

### 3.1 Backend checklist

1. **Enum value.** Add `json_schema = "json_schema"` to `V2EvalType`.

2. **Properties class.** Create `JsonSchemaProperties(BaseModel)` with `type: Literal["json_schema"] = "json_schema"` and the type-specific config fields. The class must be a Pydantic v2 `BaseModel`; JSON-serializable; carrying the `type` discriminator field.

3. **Union member.** Add `JsonSchemaProperties` to the `V2EvalConfigProperties = Annotated[Union[...], Discriminator("type")]` type alias.

4. **Adapter class.** Create `JsonSchemaAdapter(BaseEval)` implementing `run_eval`. Per C.11c (no `BaseEvalV2` fork), the adapter subclasses `BaseEval` directly. Per A2.10:
   - If the type requires an LLM call: read model fields from its own properties (like `LlmJudgeAdapter` reads from `LlmJudgeProperties.model_name`). Do NOT use the legacy `model_and_provider()` helper.
   - If the type is deterministic (no LLM): inherit `BaseEval` cleanly; never touch model fields.

5. **Registry entry.** Add `V2EvalType.json_schema: JsonSchemaAdapter` to `_V2_ADAPTER_MAP` in `registry.py`. The exhaustive match assertion will fail at test time if this is missing.

6. **Tests.** Unit tests for the properties class (validation, serialization). Integration test for the adapter (end-to-end scoring of a sample EvalInput).

### 3.2 Frontend checklist

7. **Per-type module.** Create a module exporting `{ label, icon, createForm, resultRenderer, requiresTrust }` per G.3's registry contract. `createForm` renders the type-specific authoring form in the create container (G.1). `resultRenderer` renders per-type view detail. `requiresTrust` is `false` for config-driven types; `true` for code-based types.

8. **Registry entry.** Register the module in the frontend per-type registry keyed on `"json_schema"`. The TypeScript exhaustiveness guard over `V2EvalType` will produce a compile error if this is missing.

9. **Type picker.** The type appears in the create container's type-picker list automatically (the picker iterates the registry).

### 3.3 What does NOT need to change

- **EvalConfig schema.** No modifications to `EvalConfig` itself. The new type enters through the `V2EvalConfigProperties` union.
- **Runner dispatch.** `eval_adapter_from_type` routes through `_V2_ADAPTER_MAP` automatically once the entry is added.
- **EvalRun schema.** No EvalRun changes. The new adapter produces scores that validate against the existing `EvalRun.validate_scores` mechanism.
- **EvalInput schema.** No EvalInput changes (unless the new type introduces a new input variant, which would be a separate schema addition).
- **Coexistence.** V1 EvalConfigs and existing V2 EvalConfigs are unaffected. Per A0.1, no rewriting of existing records.

---

## 4. Judge prompt template extensibility (A2.4, A2.10)

### 4.1 User-authored templates are the extension point

Every `llm_judge` EvalConfig carries a Jinja2 `prompt_template` field (`components/40`, section 3.1). Users write their own judge prompts using the reserved template variables (`final_message`, `trace`, `reference_data`, `task_input`). This is the primary extensibility surface for judge-based scoring -- users control what the judge sees and how it is asked to evaluate.

There is no closed set of judge prompts. Users can:

- Write a prompt from scratch using the template variables.
- Start from a first-party RAG template (`components/29`) and customize it.
- Start from an existing EvalConfig (clone-not-edit per G.1) and modify the prompt.

### 4.2 First-party RAG templates as starting points

`components/29_rag_judge_templates.md` defines a library of first-party RAG judge templates (faithfulness, relevance, context recall, etc.). These are **pre-authored `prompt_template` strings** shipped with Kiln as starting points. They are NOT a separate extension point or a template registry. They are presented in the builder UI's template gallery and instantiated as the `prompt_template` field of a new `llm_judge` EvalConfig.

Users can modify them after instantiation. The EvalConfig's saved `prompt_template` is the source of truth (immutable per D.3's snapshot principle); the template gallery is a convenience, not a constraint.

### 4.3 Template-level extensibility vs type-level extensibility

An important distinction: **template customization does not require a new EvalConfigType.** A user who wants to judge "Does the output cite its sources?" writes a custom `prompt_template` for an `llm_judge` config. They do not need a `citation_check` type. The `llm_judge` type + template extensibility covers the vast majority of "I want a new kind of judge" use cases.

Type-level extensibility (adding a new `V2EvalType`) is reserved for fundamentally different scoring mechanisms -- different data access patterns, different execution models (LLM vs deterministic vs code), different score production logic. Template extensibility within `llm_judge` handles variation in what the judge is asked, not how it scores.

---

## 5. Filter / extraction primitives -- internal for V2.0

### 5.1 `extract()` is a library function, not an extension point

The `extract()` helper (defined in `components/06_prereq_input_transform.md`, consumed by V2 evals per `components/40` section 1.2) evaluates Jinja2 expressions against the `EvalTaskInput` to pull values out of structured data. It is used by:

- `llm_judge` -- for `required_var` pre-checks (D.3).
- Simple-check types (`exact_match`, `pattern_match`, `contains`, `set_check`) -- for `value_expression` extraction (D.3).

`extract()` is a **stable library function** with a defined contract (Jinja2 expression in, value out). It is NOT a registry or an extension point. Users cannot register custom extraction functions. The extraction language is Jinja2 expressions; users extend extraction by writing richer Jinja2 expressions, not by plugging in new extractors.

### 5.2 Why not extensible extractors

A plugin model for extraction functions would add complexity (registration, discovery, sandboxing of user extraction code) for minimal benefit. Jinja2 expressions are expressive enough for field access, list comprehension, conditional selection, and string manipulation. Cases that exceed Jinja2's expressiveness (e.g., parsing a custom binary format from the trace) belong in `code_eval`, where the user has full Python access to the raw inputs.

### 5.3 `value_expression` is user-authored but not pluggable

Each simple-check EvalConfig carries a `value_expression: str | None` field -- a Jinja2 expression authored by the user. This is user-extensible in the sense that users write arbitrary Jinja2 expressions. It is not pluggable in the sense that users cannot swap the expression language or inject custom evaluation functions into the Jinja2 environment. The Jinja2 environment is sandboxed (no imports, no side effects) per `components/06`.

---

## 6. Scorer policy extensibility -- out of scope for V2.0 (E.36)

### 6.1 No scorer policy registry

V2.0 does not ship a scorer policy abstraction, a composite type, or a score-aggregation plugin model. Per A2.4, `composite` is deferred to post-V2. Per E.19, the composite policy registry is deferred alongside it.

### 6.2 What "scorer policy" would mean in a future version

When the `composite` EvalConfigType ships (post-V2), it will carry a `policy` field inside `CompositeProperties` that names the aggregation strategy (`tiered_60_40`, `blocking_only`, etc.). The policy registry -- if one is built -- would be internal to the composite type, not a general-purpose extension point. Named policies would be built-in functions, not third-party plugins, consistent with the closed-catalog stance.

---

## 7. V2.0 stable extension surface vs internal-only (summary)

This table summarizes what V2.0 exposes as a stable, user-facing extension point vs what is internal-only (subject to change without notice).

| Surface | V2.0 status | Who extends it | How |
|---|---|---|---|
| **Judge prompt templates** | Stable, user-extensible | Users | Author Jinja2 `prompt_template` on `llm_judge` EvalConfig |
| **Extraction expressions** (`value_expression`, `required_var`) | Stable, user-authored | Users | Write Jinja2 expressions against the reserved template variables |
| **`code_eval` scorer** | Stable, user-authored | Users (per-project) | Author Python scorer function in `code_eval` EvalConfig properties |
| **`V2EvalType` enum** | Internal, closed | Kiln team (PR required) | Add enum value + properties class + adapter + UI module |
| **`V2EvalConfigProperties` union** | Internal, closed | Kiln team (PR required) | Add properties class to union |
| **Adapter map** (`_V2_ADAPTER_MAP`) | Internal, closed | Kiln team (PR required) | Add entry to dict |
| **`extract()` helper** | Internal, stable contract | N/A (not extensible) | Library function; users write Jinja2 expressions, not custom extractors |
| **Scorer policy / composite** | Not shipped | N/A | Deferred to post-V2 with composite type |
| **Filter primitives** | Internal, closed | N/A | Not a user-facing concept; extraction via Jinja2 expressions covers the need |

---

## 8. Consolidation note: `batch_e_cross_cutting.md` decision 36

The E.36 content in `batch_e_cross_cutting.md` (decision 36 -- plugin/registry extensibility contract) is fully consolidated into this file. That scratch doc's decision 36 section covered:

- The three options (closed catalog, open registry, closed + code_eval escape hatch).
- The recommendation for option (c).
- The competitive reference (Inspect AI setuptools entry points).
- The design-file hook for `components/80`.

All of this content is captured here in sections 1-2 with greater specificity (the four architectural seams, the concrete plug-in checklist, the conditions for opening). The scratch doc can be archived per the scratch-doc archive plan in `design_dispatch.md` once all of its decisions are consolidated into their respective design files.

---

## 9. Alignment reference coverage

| Ref | Decision | Coverage in this file |
|---|---|---|
| A2.4 | V2.0 lean catalog | Section 1.1 (closed catalog of 8 types); Section 3 (how a new built-in type plugs in post-V2); Section 4.3 (template extensibility vs type extensibility distinction) |
| A2.10 | `model_and_provider` helper extraction; `BaseEval` stays generic | Section 3.1 step 4 (new adapter reads model fields from own properties per A2.10; does not use legacy helper) |
| A2.11 | Adapter registry signature change | Section 2.3 (adapter map extension seam builds on A2.11's `eval_adapter_from_type(eval_config)` signature); Section 3.1 step 5 (registry entry) |
| B.12 | Hybrid: config-first, `code_eval` as additional type | Section 1.3 (`code_eval` as per-project escape hatch); Section 7 (stable extension surface table) |
| E.36 | Plugin extensibility: closed catalog + `code_eval` for V2.0 | Sections 1-2 (primary content -- V2.0 stance, rationale, architectural seams, conditions for opening); Section 8 (consolidation of batch_e decision 36) |

---

## Opens

None. All alignment_refs are fully covered. The closed-catalog stance is clear; the seams are documented; the conditions for opening are identified. No blocking questions remain.
