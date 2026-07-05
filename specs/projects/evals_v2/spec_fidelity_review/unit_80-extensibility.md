# Spec-Fidelity Review: Unit 80-extensibility — Extensibility Contract

Requirements: 28 total — MET 22, PARTIAL 1, MISSING 0, CONTRADICTED 0, DEFERRED_OK 5, CANNOT_VERIFY 0

---

## Requirements Table

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 80-R01 | Architecture | MET | — | V2EvalType is a `str, Enum` with 8 hardcoded values | §1.1: "The `V2EvalType` enum … is hardcoded in Kiln source" | `libs/core/kiln_ai/datamodel/eval.py:67-78` — `class V2EvalType(str, Enum)` with 8 values | — |
| 80-R02 | Architecture | MET | — | V2EvalConfigProperties is an Annotated[Union[...], Discriminator("type")] with one properties class per type | §2.2: "Annotated[Union[...], Discriminator("type")] with one properties class per built-in type" | `libs/core/kiln_ai/datamodel/eval.py:226-238` — exactly this pattern with 8 classes | — |
| 80-R03 | Architecture | MET | — | _V2_ADAPTER_MAP is a dict[V2EvalType, type] for dispatch | §2.3: "_V2_ADAPTER_MAP … is a plain dict[V2EvalType, type[BaseEval]]" | `libs/core/kiln_ai/adapters/eval/registry.py:25-34` — `_V2_ADAPTER_MAP: dict[V2EvalType, type[BaseV2EvalBridge]]` with 8 entries | — |
| 80-R04 | Extensibility | DEFERRED_OK | — | No runtime discovery of third-party type values | §1.1: "No runtime discovery of third-party type values" | No plugin/entry-point/discovery code exists anywhere in the eval adapter tree | — |
| 80-R05 | Extensibility | DEFERRED_OK | — | No setuptools entry-point registration | §1.1: "No setuptools entry-point registration" | No setuptools references in eval code | — |
| 80-R06 | Extensibility | DEFERRED_OK | — | No plugin package format or marketplace | §1.1: "No plugin package format. No plugin marketplace or discovery UX." | No such code exists | — |
| 80-R07 | Architecture | MET | — | code_eval is the per-project escape hatch for custom scoring | §1.3: "code_eval is the per-project escape hatch" | `libs/core/kiln_ai/adapters/eval/v2_eval_code_eval.py` — full implementation; user Python scorer in sandbox subprocess | — |
| 80-R08 | Architecture | MET | — | code_eval code lives in EvalConfig's properties.code field as inline string | §1.3: "The code lives in the EvalConfig's properties.code field as an inline string" | `libs/core/kiln_ai/datamodel/eval.py:194` — `CodeEvalProperties.code: str` | — |
| 80-R09 | Architecture | MET | — | No built-in mechanism to share code_eval scorer across projects | §1.3: "There is no built-in mechanism to share a scorer across projects" | No cross-project sharing API exists | — |
| 80-R10 | Plug-in checklist | MET | — | Step 1: Add enum value to V2EvalType | §3.1 step 1 | `libs/core/kiln_ai/datamodel/eval.py:67-78` — pattern confirms: each type is an enum member | — |
| 80-R11 | Plug-in checklist | MET | — | Step 2: Create Properties class with type: Literal discriminator, Pydantic BaseModel | §3.1 step 2 | All 8 properties classes follow this pattern (e.g., `ExactMatchProperties(BaseModel)` with `type: Literal[V2EvalType.exact_match]` at line 93) | — |
| 80-R12 | Plug-in checklist | MET | — | Step 3: Add Properties class to V2EvalConfigProperties union | §3.1 step 3 | `libs/core/kiln_ai/datamodel/eval.py:226-238` — all 8 classes listed in the union | — |
| 80-R13 | Plug-in checklist | PARTIAL | minor | Step 4: Adapter subclasses BaseEval directly (C.11c: no BaseEvalV2 fork) | §3.1 step 4: "the adapter subclasses `BaseEval` directly. Per C.11c (no `BaseEvalV2` fork)" | All V2 adapters subclass `BaseV2EvalBridge` (e.g., `v2_eval_code_eval.py:42`), which itself subclasses `BaseEval`. `BaseV2EvalBridge` is defined at `base_eval.py:217`. | Adapters subclass `BaseV2EvalBridge`, not `BaseEval` directly. The spirit of C.11c (no separate `BaseEvalV2` replacing BaseEval) is preserved — `BaseV2EvalBridge` is a thin bridge that subclasses `BaseEval` — but the spec's "subclasses `BaseEval` directly" does not literally hold. The spec's checklist for adding a new type would need updating to say `BaseV2EvalBridge`. |
| 80-R14 | Plug-in checklist | MET | — | Step 4: LLM-based adapter reads model fields from its own properties (A2.10), not legacy helper | §3.1 step 4: "read model fields from its own properties … Do NOT use the legacy model_and_provider() helper" | `libs/core/kiln_ai/adapters/eval/v2_eval_llm_judge.py:126-127` — reads `props.model_name` and `ModelProviderName(props.model_provider)` directly | — |
| 80-R15 | Plug-in checklist | MET | — | Step 5: Add entry to _V2_ADAPTER_MAP in registry.py | §3.1 step 5 | `libs/core/kiln_ai/adapters/eval/registry.py:25-34` — all 8 entries present | — |
| 80-R16 | Plug-in checklist | MET | — | Exhaustive match assertion fails at test time if entry is missing | §3.1 step 5: "The exhaustive match assertion will fail at test time if this is missing" | `libs/core/kiln_ai/adapters/eval/test_registry.py:89-104` — `_IMPLEMENTED_V2_TYPES` parameterized test covers all 8 types. At type level, `dict[V2EvalType, type[BaseV2EvalBridge]]` typing would catch mismatches | — |
| 80-R17 | Frontend | MET | — | Frontend per-type module exports { label, icon, createForm, resultRenderer, requiresTrust } per G.3 | §3.2 step 7 | `app/web_ui/src/lib/utils/eval_types/registry.ts:59-66` — `V2EvalTypeMetadata` interface with exactly those fields (named slightly differently: `createFormComponent`, `resultRendererComponent`) | — |
| 80-R18 | Frontend | MET | — | Frontend registry keyed on type discriminator with TypeScript exhaustiveness guard | §3.2 step 8: "The TypeScript exhaustiveness guard over V2EvalType will produce a compile error if this is missing" | `app/web_ui/src/lib/utils/eval_types/registry.ts:155` — `default: return assertNever(type)` in the switch over `V2EvalType` | — |
| 80-R19 | Frontend | MET | — | Type picker iterates the registry automatically | §3.2 step 9: "The type appears in the create container's type-picker list automatically (the picker iterates the registry)" | `app/web_ui/src/routes/(app)/specs/[...]/create_eval_config/+page.svelte:486` — `{#each ALL_V2_EVAL_TYPES as evalType}` | — |
| 80-R20 | Schema stability | MET | — | New type does NOT require EvalConfig schema changes | §3.3: "No modifications to EvalConfig itself. The new type enters through the V2EvalConfigProperties union." | `libs/core/kiln_ai/datamodel/eval.py:630` — `properties: V2EvalConfigProperties | dict[str, Any] | None` — generic field, no per-type coupling | — |
| 80-R21 | Schema stability | MET | — | New type does NOT require EvalRun schema changes | §3.3: "No EvalRun changes. The new adapter produces scores that validate against the existing EvalRun.validate_scores mechanism." | `libs/core/kiln_ai/datamodel/eval.py:530-547` — `validate_scores` checks against parent Eval's `output_scores` generically, no type-specific logic | — |
| 80-R22 | Schema stability | MET | — | Runner dispatch routes through _V2_ADAPTER_MAP automatically | §3.3: "eval_adapter_from_type routes through _V2_ADAPTER_MAP automatically once the entry is added" | `libs/core/kiln_ai/adapters/eval/registry.py:70` — `adapter_cls = _V2_ADAPTER_MAP.get(v2_type)` | — |
| 80-R23 | Judge templates | MET | — | Every llm_judge EvalConfig carries a Jinja2 prompt_template field | §4.1: "Every llm_judge EvalConfig carries a Jinja2 prompt_template field" | `libs/core/kiln_ai/datamodel/eval.py:86` — `LlmJudgeProperties.prompt_template: str`; rendered via Jinja2 at `v2_eval_llm_judge.py:110` | — |
| 80-R24 | Judge templates | DEFERRED_OK | — | RAG templates deferred from V2.0 | §4.2: "Deferred from V2.0 -- RAG templates are not shipped in V2.0" | No RAG template code in the V2 eval tree | — |
| 80-R25 | Extraction | MET | — | extract() is a stable library function, not an extension point; users cannot register custom extraction functions | §5.1: "extract() is a stable library function … Users cannot register custom extraction functions" | `libs/core/kiln_ai/utils/jinja_engine.py:80-98` — plain function, no registry/plugin mechanism | — |
| 80-R26 | Extraction | MET | — | Jinja2 environment is sandboxed (no imports, no side effects) | §5.3: "The Jinja2 environment is sandboxed (no imports, no side effects)" | `libs/core/kiln_ai/utils/jinja_engine.py:36-40` — `_expression_env = SandboxedEnvironment(...)` from `jinja2.sandbox` | — |
| 80-R27 | Scorer policy | DEFERRED_OK | — | No scorer policy registry; composite type deferred | §6.1: "V2.0 does not ship a scorer policy abstraction, a composite type, or a score-aggregation plugin model" | No composite/policy code anywhere in eval tree | — |
| 80-R28 | Frontend/Backend mirror | MET | — | Front and back registries mirror each other (same 8 types) | §2.4 / focus notes: "Front/back registries mirror each other" | Backend: `registry.py:25-34` (8 entries). Frontend: `registry.ts:39-48` `ALL_V2_EVAL_TYPES` (8 entries). Same 8 type strings in both. | — |

---

## Verifier-Added Requirements

(Re-scan found no additional binding requirements missed above. The spec's seam documentation in sections 2.1-2.5 is descriptive/future-oriented and explicitly non-binding for V2.0.)

---

## Notes

- **80-R13 (PARTIAL):** The spec states adapters "subclass `BaseEval` directly" per C.11c. In practice, all V2 adapters subclass `BaseV2EvalBridge` (a thin bridge inheriting from `BaseEval`). The bridge exists to provide a shared `evaluate()` -> `run_eval()` wiring so V2 adapters don't duplicate that plumbing. The spirit of C.11c ("no `BaseEvalV2` fork" that replaces or splits from `BaseEval`) is preserved — `BaseV2EvalBridge` IS `BaseEval`, just with a thin adapter pattern. The spec's "how to add a new type" checklist (§3.1 step 4) would point a developer to subclass `BaseV2EvalBridge`, not `BaseEval`, so the spec is mildly inaccurate as documentation. Impact: a developer following the spec literally would subclass `BaseEval` and then need to figure out `BaseV2EvalBridge` themselves — minor friction, easily resolved.
