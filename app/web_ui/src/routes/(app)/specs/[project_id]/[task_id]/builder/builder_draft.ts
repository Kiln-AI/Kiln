// Draft persistence for the eval-builder wizard (the SDG synth pattern:
// IndexedDB, per-task key, silent restore). Navigation or a reload can no
// longer destroy a session's authoring work: the spec fields and the
// approved batch plan restore silently; the batch-tag bookkeeping restores
// so chains a lost session left on disk are still cleaned up by the next
// drive (without it they'd be orphaned forever). Driven/review state is
// deliberately NOT persisted — it depends on disk state that can change
// under a saved draft, so restore never lands past the plan screen.

import type { SpecType } from "$lib/types"
import type { SuggestedEdit } from "../spec_utils"

// A generated synthetic-user case as the wire carries it: the seed message,
// the persona blob, and the plan scenario it came from.
export type SyntheticUserCaseWire = {
  seed_prompt: string
  synthetic_user_info: string
  scenario_index?: number | null
}

// The generate_cases output, cached against exactly the inputs it depends
// on (the approved prompts + the spec text — the run config plays no part
// in persona generation). A re-drive with both unchanged reuses the cases
// instead of re-paying the multi-minute copilot generation, which makes the
// fix-config-then-drive-again recovery loop fast.
export type CachedSuCases = {
  prompts_json: string
  spec_text: string
  cases: SyntheticUserCaseWire[]
}

// The cached cases iff they were generated from EXACTLY this plan and spec
// (byte-compare); anything else means regenerate. Fresh variation on the
// same scenarios is deliberately not offered — that's what New Batch Plan
// is for.
export function reusable_cached_cases(
  cache: CachedSuCases | null,
  approved_prompts: string[],
  spec: string,
): SyntheticUserCaseWire[] | null {
  if (!cache || cache.cases.length === 0) return null
  if (cache.spec_text !== spec) return null
  if (cache.prompts_json !== JSON.stringify(approved_prompts)) return null
  return cache.cases
}

export type BuilderDraft = {
  // Step 1-3 — spec authoring.
  description: string
  spec_type: SpecType
  name: string
  property_values: Record<string, string | null>
  refined_property_values: Record<string, string | null>
  suggested_edits: Record<string, SuggestedEdit>
  not_incorporated_feedback: string
  // Step 4 — the approved plan (minutes of copilot work to recreate).
  batch_plan: { prompts: string[]; summary: string } | null
  batch_plan_edited: boolean
  // The plan's generated synthetic users (more minutes) — reused on drive
  // while plan+spec are byte-unchanged, revalidated in reusable_cached_cases.
  cached_su_cases: CachedSuCases | null
  // Batch-tag bookkeeping — a CORRECTNESS carry, not convenience: these
  // name chains already on disk. multi_turn_batch_tag is the live batch;
  // undeleted_batch_tags is the delete-on-next-drive cleanup list.
  multi_turn_batch_tag: string | null
  undeleted_batch_tags: string[]
}

export const EMPTY_BUILDER_DRAFT: BuilderDraft = {
  description: "",
  spec_type: "issue",
  name: "",
  property_values: {},
  refined_property_values: {},
  suggested_edits: {},
  not_incorporated_feedback: "",
  batch_plan: null,
  batch_plan_edited: false,
  cached_su_cases: null,
  multi_turn_batch_tag: null,
  undeleted_batch_tags: [],
}

export function builder_draft_key(project_id: string, task_id: string): string {
  return `eval_builder_draft_${project_id}_${task_id}_v1`
}

// A dev-only fetch mock may mark the window when installed. Drafts are
// gated on it in BOTH directions: canned mock state must never persist into
// a real session, and a real draft must never restore under the mock.
// Checking the flag rather than importing keeps mock code out of production
// builds.
export function builder_mock_active(): boolean {
  return (
    typeof window !== "undefined" && "__KILN_BUILDER_MOCK_ACTIVE__" in window
  )
}

function record_has_content(record: Record<string, string | null>): boolean {
  return Object.values(record).some((v) => (v ?? "").trim() !== "")
}

// Whether a stored draft carries anything worth restoring. Batch tags alone
// count: even a draft with no authoring content still names on-disk chains
// that the next drive must clean up.
export function draft_has_content(draft: BuilderDraft): boolean {
  return (
    draft.description.trim() !== "" ||
    draft.name.trim() !== "" ||
    record_has_content(draft.property_values) ||
    record_has_content(draft.refined_property_values) ||
    Object.keys(draft.suggested_edits).length > 0 ||
    draft.batch_plan !== null ||
    draft.multi_turn_batch_tag !== null ||
    draft.undeleted_batch_tags.length > 0
  )
}

// The furthest SAFE step a restored draft can land on — never past the plan
// screen (step 4), and never into review: review state isn't persisted, and
// presenting stale results would be worse than replaying a drive.
//   - a plan exists → the plan screen ("generate")
//   - refine output exists → "refine" (clarify Q&A isn't persisted, so a
//     draft that died mid-clarify restarts from the description)
//   - otherwise → "describe" with the description prefilled
export type RestoreStep = "describe" | "refine" | "generate"

export function restore_step(draft: BuilderDraft): RestoreStep {
  if (draft.batch_plan !== null && draft.batch_plan.prompts.length > 0) {
    return "generate"
  }
  if (
    record_has_content(draft.refined_property_values) ||
    Object.keys(draft.suggested_edits).length > 0
  ) {
    return "refine"
  }
  return "describe"
}

// A fresh draft that KEEPS the batch-tag bookkeeping. Reset must not wipe
// the tags: they name chains already on disk, and delete-on-next-drive is
// the only thing that ever cleans those up — a full wipe would orphan them
// forever (the leak the draft's tag persistence exists to prevent).
export function reset_draft_keeping_tags(draft: BuilderDraft): BuilderDraft {
  return {
    ...EMPTY_BUILDER_DRAFT,
    multi_turn_batch_tag: draft.multi_turn_batch_tag,
    undeleted_batch_tags: draft.undeleted_batch_tags,
  }
}

// The Evals page's create button advertises a resumable draft (the silent
// restore already happens on builder entry; this makes it discoverable).
// Copilot-gated: without copilot the button routes to the legacy flow,
// where no draft exists.
export function create_eval_button_label(
  has_copilot: boolean,
  has_draft: boolean,
): string {
  return has_copilot && has_draft ? "Continue Eval Draft" : "Create Eval"
}
