export const meta = {
  name: 'evals-v2-spec-fidelity-cr',
  description: 'Spec-fidelity deep CR for Evals V2: enumerate every spec requirement, verify each against real code, adversarially confirm gaps',
  phases: [
    { title: 'Extract requirements', detail: 'one agent per spec component → atomic requirement checklist (UX/layout/cut directives first-class)' },
    { title: 'Verify vs code', detail: 'per component, open real code and render a verdict per requirement (file:line)' },
    { title: 'Adversarial confirm', detail: 'independent skeptic tries to refute each non-MET finding' },
  ],
}

const SPEC = '/Users/scosman/Dropbox/workspace/kiln_new/specs/projects/evals_v2'
const REPO = '/Users/scosman/Dropbox/workspace/kiln_new'

// A known true divergence, used ONLY to calibrate what "CONTRADICTED" looks like.
// Reviewers must find their own findings, not rubber-stamp this one.
const CALIBRATION = `CALIBRATION EXAMPLE of the class of miss this review exists to catch (do NOT treat as the only thing to look for): components/70 §1 and §2 specify that the "Test Run" pane must let the user PICK A RECENT DATASET ITEM to run the judge on, and explicitly state "Manual free-text input is cut." The implementation instead built four free-text textareas (final_message / task_input / trace / reference_data) in a collapse below the form, with no dataset-item picker. That is a CONTRADICTED requirement (the spec demanded a picker and forbade free-text; the code does the opposite) even though the code "works". A correctness-only review missed it. Layout, placement, interaction-design, and "X is cut" directives are REQUIREMENTS, not decoration.`

const UNITS = [
  {
    id: '05-thinking-formatter',
    title: 'Prereq: SingleTurnR1ThinkingFormatter fix',
    specFiles: [`${SPEC}/components/05_prereq_thinking_formatter_fix.md`],
    codePointers: [
      'libs/core/kiln_ai/adapters/chat/chat_formatter.py — SingleTurnR1ThinkingFormatter (~line 253), forward_thinking_instructions param + deprecation warning',
      'libs/core/kiln_ai/adapters/chat/test_chat_formatter.py',
      'libs/core/kiln_ai/adapters/model_adapters/test_base_adapter.py — test_build_chat_formatter_forward_thinking_instructions',
    ],
    notes: 'Opt-in forward_thinking_instructions; V1 default behavior must be unchanged; reasoning models receive thinking instructions when flag set.',
  },
  {
    id: '10-data-model',
    title: 'Data model (Eval/EvalConfig/EvalInput/EvalRun + V2 union)',
    specFiles: [`${SPEC}/components/10_data_model.md`],
    codePointers: ['libs/core/kiln_ai/datamodel/eval.py — all V2 models, enums, properties classes, validators'],
    notes: 'Verify EVERY field name/type/default, each enum value, the discriminated V2EvalConfigProperties union, EvalInput/EvalInputData variants (single-turn / multi-turn-synthetic), EvalRun additive fields, validators (mutual-exclusivity / XOR / skip-relaxed). Field-by-field — do not summarize.',
  },
  {
    id: '15-coexistence',
    title: 'V1/V2 coexistence',
    specFiles: [`${SPEC}/components/15_v1_v2_coexistence.md`],
    codePointers: [
      'libs/core/kiln_ai/datamodel/eval.py — dispatch_properties_parsing / validate_properties / validate_json_serializable V2 bypass',
      'libs/core/kiln_ai/datamodel/dataset_filters.py — EvalInputFilter protocol/registry (~line 192)',
      'libs/core/kiln_ai/adapters/eval/registry.py — legacy_eval_adapter_from_type vs v2_eval_adapter_from_config',
      'libs/core/kiln_ai/adapters/eval/eval_runner.py — _source_mode (~line 94)',
    ],
    notes: 'V1 BC is "absolute" (D.5): verify zero V1 behavior change for read+execution. Additive optional fields load as None for V1. XOR validators. DatasetFilter stays TaskRun-only. TaskRun→EvalInput runtime translation (B2.1). Each numbered decision (A2.x, D.x, K.x, B2.1) is a requirement.',
  },
  {
    id: '20-types-overview',
    title: 'Eval config types overview / adapter contract',
    specFiles: [`${SPEC}/components/20_eval_config_types_overview.md`],
    codePointers: [
      'libs/core/kiln_ai/adapters/eval/registry.py — _V2_ADAPTER_MAP, v2_eval_adapter_from_config',
      'libs/core/kiln_ai/adapters/eval/base_eval.py — BaseV2EvalBridge (evaluate() contract)',
      'libs/core/kiln_ai/adapters/eval/eval_utils/scoring_utils.py',
    ],
    notes: 'Two-level dispatch (config_type → properties.type). Adapter return tuple (scores, skipped_reason, skipped_detail). Scores validate against parent Eval.output_scores. All 8 types registered.',
  },
  {
    id: '21-llm-judge',
    title: 'Type: enhanced llm_judge',
    specFiles: [`${SPEC}/components/21_type_llm_judge.md`],
    codePointers: [
      'libs/core/kiln_ai/adapters/eval/v2_eval_llm_judge.py',
      'libs/core/kiln_ai/adapters/eval/eval_utils/scoring_utils.py',
      'libs/core/kiln_ai/datamodel/eval.py — LlmJudgeProperties',
      'app/web_ui/src/lib/components/eval_types/llm_judge_form.svelte',
      'app/web_ui/src/lib/components/eval_types/llm_judge_result.svelte',
    ],
    notes: 'Per-criterion pass/fail verdicts, g_eval toggle, Jinja2 prompt_template, structured output mode selection, trace condensation, reference templating, forward_thinking wiring, default system_prompt="You are an evaluator." set at creation, system_prompt NOT exposed in the create form (§6.2).',
  },
  {
    id: '22-deterministic',
    title: 'Types: 6 deterministic/agent checks',
    specFiles: [`${SPEC}/components/22_type_deterministic_basics.md`, `${SPEC}/reference/batch_agent_eval_expansion.md`],
    codePointers: [
      'libs/core/kiln_ai/adapters/eval/v2_eval_{exact_match,pattern_match,contains,set_check,tool_call_check,step_count_check}.py',
      'libs/core/kiln_ai/adapters/eval/eval_utils/v2_eval_helpers.py — build_binary_scores, extract_value, check_reference_key',
      'libs/core/kiln_ai/datamodel/eval.py — the 6 *Properties classes',
      'app/web_ui/src/lib/components/eval_types/{type}_form.svelte (6)',
    ],
    notes: 'For EACH of the 6 types verify: properties shape, value_expression/extract behavior, literal-vs-reference_key XOR, case sensitivity, all modes (pattern must/must-not, contains, set subset/superset/equal, tool_call match modes any/all/ordered/never + on_unexpected_tools + per-arg ArgMatch, step_count count types + min/max). Forms §3.1 field-by-field.',
  },
  {
    id: '27-code-eval',
    title: 'Type: code_eval (Beta)',
    specFiles: [`${SPEC}/components/27_type_code_eval.md`],
    codePointers: [
      'libs/core/kiln_ai/adapters/eval/v2_eval_code_eval.py — trust gate, score validation',
      'libs/core/kiln_ai/adapters/eval/sandbox_worker.py — multiprocessing spawn, timeout, stdout/stderr capture',
      'libs/core/kiln_ai/adapters/eval/eval_helpers.py — KilnEvalHelpers (all helper methods)',
      'libs/core/kiln_ai/datamodel/eval.py — CodeEvalProperties',
      'app/desktop/studio_server/eval_api.py — trust endpoints (~line 1743)',
      'app/web_ui/src/lib/components/eval_types/code_eval_form.svelte / code_eval_result.svelte / code_eval_helpers.ts',
    ],
    notes: 'Scorer contract: score(output, trace, reference_data, task_input, kiln) -> dict[str,float]. Verify EACH KilnEvalHelpers method named in spec exists. multiprocessing spawn worker + freeze_support, wall-clock timeout (join/kill), limited imports (refuses to run what it would refuse to save), return-shape validation, trust gate ephemeral/in-memory/window-scoped/re-asked-on-launch, CodeMirror6 lazy-loaded + Python label, minimal valid example loaded on open, "See examples" tabbed gallery with "Use this template", format/lint buttons CUT, Beta label, "Save Without Testing" modal copy, trust modal copy.',
  },
  {
    id: '40-template-extraction',
    title: 'Template + extraction layer',
    specFiles: [`${SPEC}/components/40_template_and_extraction.md`, `${SPEC}/components/06_prereq_input_transform.md`],
    codePointers: [
      'libs/core/kiln_ai/datamodel/eval.py — EvalTaskInput; validate_v2_templates_and_expressions',
      'libs/core/kiln_ai/utils/jinja_engine.py — extract(), compile_template_or_raise, StrictUndefined',
      'libs/core/kiln_ai/adapters/eval/eval_utils/v2_eval_helpers.py — extract_value, check_required_vars',
      'libs/core/kiln_ai/adapters/eval/v2_eval_llm_judge.py — template render',
    ],
    notes: 'EvalTaskInput assembly, required_var skip-with-reason precheck, save-time template/expression compilation, extract() helper semantics, V1 backwards-compat for templates (existing hardcoded f-string path untouched).',
  },
  {
    id: '45-runner',
    title: 'Runner architecture',
    specFiles: [`${SPEC}/components/45_runner_architecture.md`],
    codePointers: [
      'libs/core/kiln_ai/adapters/eval/eval_runner.py — EvalJob, __init__ source branching, collect_tasks dispatch, run_job, _run_v2_job skip conditions, persistence',
      'libs/core/kiln_ai/adapters/eval/base_eval.py — run_task(TaskRun|EvalInput)',
    ],
    notes: 'EvalInput vs TaskRun source branching (C.runner.3), two-level dispatch, multi-config orchestration / candidate calibration, ALL skip conditions (type_not_available, incompatible_input_shape, eval_config_eval over EvalInput, missing reference), persists EvalRun with skipped_reason, B2.1 TaskRun→EvalInput translation, EvalRun.dataset_id provenance (A2.6).',
  },
  {
    id: '50-reference-data',
    title: 'Reference data',
    specFiles: [`${SPEC}/components/50_reference_data.md`],
    codePointers: [
      'libs/core/kiln_ai/datamodel/eval.py — EvalInput.reference, EvalRun.reference_data, EvalTaskInput.reference_data',
      'libs/core/kiln_ai/adapters/eval/eval_utils/v2_eval_helpers.py — check_reference_key',
    ],
    notes: 'Flat dict shape (NOT per-config namespaced sub-dicts — that was rejected), missing-key handled via skip (not dataset-level schema enforcement), naming guidelines, multi-config consumption.',
  },
  {
    id: '70a-create-flow',
    title: 'UI: create container, type picker, forms, test-run panel',
    specFiles: [`${SPEC}/components/70_builder_and_onboarding.md`],
    codePointers: [
      'app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/[spec_id]/[eval_id]/create_eval_config/+page.svelte — container, type picker, test-run panel',
      'app/web_ui/src/lib/utils/eval_types/registry.ts',
      'app/web_ui/src/lib/api/v2_eval_api.ts — testV2Eval, createEvalConfig',
      'app/desktop/studio_server/eval_api.py — test_v2_eval endpoint (~line 970)',
      'app/web_ui/src/lib/components/eval_types/*_form.svelte (8 forms incl. code_eval_form)',
    ],
    notes: 'HIGHEST-RISK UNIT — this is where the known miss lives; be exhaustive. §1 Layout: left=authoring component, right="Test Run". §1 responsibility split: CONTAINER loads test data = recent dataset items. §2 Test Run = lists recent dataset items to PICK from; "Manual free-text input is cut"; reference data via an Advanced expander; trace comes from selected dataset item. Empty-dataset state: "Run your task to generate sample inputs" → Save-Without-Testing is the only path. Spinner + Cancel during run. Return-shape check vs output_scores enables Save; "Save Without Testing" confirm modal. Type picker: "LLM as Judge (recommended)" first then the rest; NO applicability filtering (all types listed); Back returns to picker. Clone-not-edit + prefill-from-existing. system_prompt not exposed. Deterministic form layouts §3.1 field-by-field.',
  },
  {
    id: '70b-view-surfaces',
    title: 'UI: result renderers, registry, config view, comparison',
    specFiles: [`${SPEC}/components/70_builder_and_onboarding.md`],
    codePointers: [
      'app/web_ui/src/routes/(app)/specs/.../[eval_config_id]/[run_config_id]/run_result/+page.svelte',
      'app/web_ui/src/lib/components/eval_types/*_result.svelte (8) + eval_result_scores.svelte',
      'app/web_ui/src/routes/(app)/specs/.../[eval_id]/+page.svelte (eval detail)',
      'app/web_ui/src/routes/(app)/specs/.../[eval_id]/eval_configs/+page.svelte',
      'app/web_ui/src/lib/components/run_config_comparison_table.svelte',
      'app/web_ui/src/lib/utils/eval_types/registry.ts — resultRenderer, exhaustive enum binding',
    ],
    notes: '§4 renderer registry keyed on properties.type; EXHAUSTIVE over V2EvalType (compile-time never + runtime assert) — a backend type with no UI module must FAIL LOUDLY, not render blank. §4.1 the ONE firm requirement: every result renderer shows the score(s) against output_scores AND skip state (skipped_reason) when set (rest of §4.1 table is illustrative, NOT binding — do not flag illustrative items as gaps, but DO verify the firm requirement). §4.3 read-only config-detail view in scope. Mixed-type display tolerated. §4.2 affected routes all integrated. Thinking column conditional on intermediate_outputs.',
  },
  {
    id: '80-extensibility',
    title: 'Extensibility contract',
    specFiles: [`${SPEC}/components/80_extensibility_contract.md`],
    codePointers: [
      'libs/core/kiln_ai/adapters/eval/registry.py — closed _V2_ADAPTER_MAP',
      'app/web_ui/src/lib/utils/eval_types/registry.ts — assertNever exhaustiveness',
      'libs/core/kiln_ai/adapters/eval/v2_eval_code_eval.py — escape hatch',
    ],
    notes: 'Closed catalog + code_eval escape hatch for V2.0. The documented "how a new built-in type plugs in" seam must actually hold in code. No runtime plugin discovery shipped (E.36). Front/back registries mirror each other. EvalRun schema unchanged by new adapters.',
  },
  {
    id: '85-observability',
    title: 'Observability & audit',
    specFiles: [`${SPEC}/components/85_observability_and_audit.md`],
    codePointers: [
      'libs/core/kiln_ai/datamodel/eval.py — SkippedReason enum',
      'libs/core/kiln_ai/adapters/eval/eval_runner.py — skip emission',
      'app/desktop/studio_server/eval_api.py — ScoreSummary n_used/n_excluded aggregation (~lines 256, 415, 581, 1619)',
    ],
    notes: 'SkippedReason enum has every reason the spec names. Skip records persisted on EvalRun. On-read aggregation exposes n_used / n_excluded. Score provenance via existing parent_of chain. Statistical comparison primitives correctly DEFERRED (absence is correct).',
  },
  {
    id: 'deferred-and-cut',
    title: 'Negative requirements: deferred / out-of-scope / cut directives',
    specFiles: [
      `${SPEC}/components/00_overview.md`,
      `${SPEC}/implementation_plan.md`,
    ],
    codePointers: [
      'grep across repo: source_task_run_id (must be ABSENT on EvalInput), composite/threshold/json_schema/event_ordering/embedding_similarity/dag_metric (must NOT be in V2 registry)',
      'libs/core/kiln_ai/adapters/eval/registry.py (exactly 8 V2 types)',
      'app/web_ui/src/lib/components/eval_types/code_eval_form.svelte (no format/lint buttons)',
      'app/web_ui/src/lib/components/eval_types/llm_judge_form.svelte (no system_prompt field)',
    ],
    notes: 'NEGATIVE-REQUIREMENT SWEEP — findings run BOTH directions: (a) out-of-scope items that WERE built = scope-creep findings (feedback/triage, goal-first questionnaire, right-sizing mechanism, deferred eval types, statistical primitives, dataset versioning, runtime plugin discovery, RAG templates inside evals_v2 rather than /specs/projects/rag_templates); (b) in-spec "X is cut/not exposed/deferred" directives that were VIOLATED (manual free-text in test-run, format/lint buttons, system_prompt in form, source_task_run_id on EvalInput). Confirm each deferral is genuinely absent OR genuinely present-when-it-should-be.',
  },
  {
    id: 'functional-arch-crosscut',
    title: 'Functional spec + architecture cross-cut',
    specFiles: [`${SPEC}/functional_spec.md`, `${SPEC}/architecture.md`],
    codePointers: ['broad — trace each top-level requirement to its owning code'],
    notes: 'Catch cross-cutting requirements not owned by a single component file. Flag any functional-spec / architecture requirement with no traceable implementation. Avoid double-counting items already owned by a component unit; focus on the connective tissue and end-to-end flows.',
  },
]

const CATEGORY = {
  type: 'string',
  enum: ['data_model', 'api', 'adapter_behavior', 'runner', 'validation', 'ux_layout', 'ux_interaction', 'cut_or_deferred', 'empty_state', 'error_handling', 'test_expectation', 'other'],
}
const SEVERITY = { type: 'string', enum: ['critical', 'major', 'minor'] }

const REQ_CHECKLIST = {
  type: 'object',
  required: ['unit', 'requirements'],
  properties: {
    unit: { type: 'string' },
    requirements: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'requirement', 'spec_quote', 'spec_location', 'category', 'severity_if_missing', 'expected_locus'],
        properties: {
          id: { type: 'string', description: 'e.g. 70a-R03' },
          requirement: { type: 'string', description: 'crisp restatement of one atomic requirement' },
          spec_quote: { type: 'string', description: 'short exact quote from the spec proving this requirement' },
          spec_location: { type: 'string', description: 'section heading or anchor in the spec file' },
          category: CATEGORY,
          severity_if_missing: SEVERITY,
          expected_locus: { type: 'string', description: 'where in the codebase this should be implemented' },
        },
      },
    },
  },
}

const VERDICT = { type: 'string', enum: ['MET', 'PARTIAL', 'MISSING', 'CONTRADICTED', 'DEFERRED_OK', 'CANNOT_VERIFY'] }

const VERDICTS = {
  type: 'object',
  required: ['unit', 'verdicts'],
  properties: {
    unit: { type: 'string' },
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'requirement', 'category', 'verdict', 'severity', 'evidence', 'divergence', 'source'],
        properties: {
          id: { type: 'string' },
          requirement: { type: 'string' },
          category: CATEGORY,
          verdict: VERDICT,
          severity: SEVERITY,
          evidence: { type: 'string', description: 'file:line citations + what the code actually does' },
          divergence: { type: 'string', description: 'for non-MET: precisely how code diverges from spec; empty for MET' },
          source: { type: 'string', enum: ['checklist', 'verifier_added'], description: 'verifier_added = a requirement the extractor missed but you found' },
        },
      },
    },
  },
}

const REFUTE = {
  type: 'object',
  required: ['id', 'upheld', 'confidence', 'corrected_verdict', 'corrected_severity', 'reasoning', 'evidence'],
  properties: {
    id: { type: 'string' },
    upheld: { type: 'boolean', description: 'true = the gap finding survives refutation and is real' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    corrected_verdict: VERDICT,
    corrected_severity: SEVERITY,
    reasoning: { type: 'string' },
    evidence: { type: 'string', description: 'file:line you checked while trying to refute' },
  },
}

function extractPrompt(u) {
  return `You are auditing the Kiln "Evals V2" project for SPEC FIDELITY. Your job in this step is REQUIREMENT EXTRACTION for one spec unit. Do not look at code yet.

Spec unit: ${u.id} — ${u.title}
Read these spec file(s) IN FULL: ${u.specFiles.join(', ')}
Focus notes: ${u.notes}

${CALIBRATION}

Enumerate EVERY discrete requirement the spec states for this unit. Rules:
- One atomic requirement per entry. Split compound sentences. A form field, a layout placement, a default value, an enum member, a modal's copy, an empty-state message, a "this is cut" directive — each is its own requirement.
- Treat UX / layout / interaction-design guidance as FIRST-CLASS requirements (which pane, what order, what affordance, what the user picks vs types). A prior review dropped exactly these and missed real divergences.
- Treat negative requirements ("X is cut", "not exposed", "deferred", "do not build") as FIRST-CLASS — they are testable.
- Distinguish BINDING requirements from explicitly-illustrative guidance. If the spec says something is "illustrative", "not a binding layout", or "agent's call", record it with severity minor and note it is illustrative, so the verifier won't flag it as a gap.
- Quote the spec verbatim (short) in spec_quote for each.
- Number ids like ${u.id}-R01, ${u.id}-R02, ...
- Be exhaustive. Aim to miss nothing; over-extraction is fine, the verifier will sort it out.

Return the structured checklist.`
}

function verifyPrompt(u, checklist) {
  const reqs = (checklist && checklist.requirements) || []
  return `You are auditing Kiln "Evals V2" for SPEC FIDELITY. This is the CODE-VERIFICATION step for one spec unit. You MUST open the real code and check each requirement against it. Repo root: ${REPO}.

Spec unit: ${u.id} — ${u.title}
Authoritative spec file(s) (re-read as needed): ${u.specFiles.join(', ')}
Code starting pointers (explore beyond these as needed; verify, do not trust names):
${u.codePointers.map((p) => '  - ' + p).join('\n')}
Focus notes: ${u.notes}

${CALIBRATION}

Here is the extracted requirement checklist to verify (JSON):
${JSON.stringify(reqs)}

For EACH requirement, open the implementing code and decide a verdict:
- MET — code does what the spec says, the way the spec says it (including placement/UX/copy where specified).
- PARTIAL — partially implemented or implemented differently in a way that drops part of the intent.
- MISSING — no implementation found.
- CONTRADICTED — code does something that conflicts with the spec (e.g. free-text input where the spec demanded a dataset-item picker and forbade free-text).
- DEFERRED_OK — spec says this is cut/deferred AND the code correctly omits it (this is a PASS, record as DEFERRED_OK).
- CANNOT_VERIFY — could not determine from code in reasonable effort (say why).

Hard rules:
- TOUCH THE CODE for every requirement. Cite concrete file:line in evidence. Do NOT infer from filenames.
- "It works / tests pass" is NOT sufficient for MET if the spec's stated approach/UX/placement differs. Fidelity to the spec's design is the bar.
- Do NOT flag explicitly-illustrative guidance as a gap; mark such items MET or note they are illustrative.
- After processing the checklist, RE-SCAN the spec file yourself for any BINDING requirement the checklist missed — especially UX/layout/interaction and "X is cut" directives — and add verdicts for them with source="verifier_added".
- Keep evidence concise but specific (file:line + 1 sentence). Keep divergence empty for MET/DEFERRED_OK.

Return the structured verdicts for every requirement (checklist + any verifier_added).`
}

function refutePrompt(u, gap) {
  return `You are an ADVERSARIAL VERIFIER (skeptic) on a spec-fidelity audit of Kiln "Evals V2". Repo root: ${REPO}. A prior reviewer flagged a spec requirement as NOT fully met. Your job is to TRY HARD TO REFUTE that finding — prove it is actually implemented, or that the reviewer misread the spec, or that the spec itself marks it cut/deferred/illustrative so the omission is correct.

Spec unit: ${u.id} — ${u.title}
Spec file(s): ${u.specFiles.join(', ')}

The flagged finding (JSON):
${JSON.stringify(gap)}

Do your own code search and your own spec read. Then:
- If you find the requirement IS implemented (cite file:line) → set upheld=false, corrected_verdict=MET.
- If the spec marks it illustrative/deferred/cut so the code is correct → upheld=false, corrected_verdict=DEFERRED_OK.
- If it is partially there → upheld=true but corrected_verdict=PARTIAL with what's missing.
- If the gap is real and as described → upheld=true, keep the verdict.
Default to upheld=true ONLY if you genuinely cannot refute it. Be specific; cite file:line you checked. Adjust corrected_severity to reflect real user impact (a contradicted core UX flow is major/critical; a missing minor affordance is minor).`
}

// ---- Run: pipeline so each unit flows extract → verify → confirm without barriers ----
log(`Spec-fidelity CR starting: ${UNITS.length} spec units → extract → verify → adversarial-confirm`)

const results = await pipeline(
  UNITS,
  // Stage 1: extract requirements
  (u) => agent(extractPrompt(u), { label: `extract:${u.id}`, phase: 'Extract requirements', schema: REQ_CHECKLIST }),
  // Stage 2: verify against real code
  (checklist, u) =>
    agent(verifyPrompt(u, checklist), { label: `verify:${u.id}`, phase: 'Verify vs code', schema: VERDICTS }).then((v) => ({
      unit: u,
      checklist,
      verify: v,
    })),
  // Stage 3: adversarially confirm each non-MET finding
  (vr, u) => {
    const verdicts = (vr && vr.verify && vr.verify.verdicts) || []
    const gaps = verdicts.filter((x) => ['PARTIAL', 'MISSING', 'CONTRADICTED'].includes(x.verdict))
    log(`${u.id}: ${verdicts.length} requirements checked, ${gaps.length} gaps → adversarial confirm`)
    return parallel(
      gaps.map((g) => () =>
        agent(refutePrompt(u, g), { label: `confirm:${u.id}:${g.id}`, phase: 'Adversarial confirm', schema: REFUTE })
          .then((r) => ({ ...g, confirm: r }))
          .catch(() => ({ ...g, confirm: null })),
      ),
    ).then((confirmed) => ({
      unit: u.id,
      title: u.title,
      requirement_count: verdicts.length,
      met_count: verdicts.filter((x) => x.verdict === 'MET' || x.verdict === 'DEFERRED_OK').length,
      all_verdicts: verdicts,
      confirmed_gaps: confirmed.filter(Boolean),
    }))
  },
)

const clean = results.filter(Boolean)
const upheld = []
for (const r of clean) {
  for (const g of r.confirmed_gaps || []) {
    if (g.confirm && g.confirm.upheld) upheld.push({ unit: r.unit, ...g })
  }
}
log(`Done: ${clean.length}/${UNITS.length} units completed; ${upheld.length} adversarially-upheld gaps`)

return { units: clean, upheld_gaps: upheld }
