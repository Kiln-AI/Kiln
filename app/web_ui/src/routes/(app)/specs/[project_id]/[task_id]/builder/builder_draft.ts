// Draft persistence for the eval-builder wizard (the SDG synth pattern:
// IndexedDB, per-task key, silent restore). Navigation or a reload can no
// longer destroy a session's authoring work: the spec fields and the
// approved batch plan restore silently; the batch-tag bookkeeping restores
// so chains a lost session left on disk are still cleaned up by the next
// drive (without it they'd be orphaned forever). Driven/review state is
// deliberately NOT persisted — it depends on disk state that can change
// under a saved draft, so restore never lands past the plan screen.

import type { JudgeConfig, ModelChoice } from "$lib/eval/default_judge"
import type { KilnAgentRunConfigProperties, OpenEnvReset } from "$lib/types"
import type { SuggestedEdit } from "../spec_utils"
import type { GroundingDrop } from "./batch_plan_guidance"
import type { BatchSize } from "./batch_profiles"

// A generated synthetic-user case as the wire carries it: the seed message,
// the persona blob, and the plan scenario it came from. leaf_run_id is absent
// until the case has been driven, which is when the run exists. A case
// grounded in an OpenEnv server also carries the episode it runs in and the
// judge guidance written from that episode's data.
export type SyntheticUserCaseWire = {
  seed_prompt: string
  synthetic_user_info: string
  scenario_index?: number | null
  leaf_run_id?: string
  openenv_reset?: OpenEnvReset | null
  judge_guidance?: string | null
  // A grounded case's rehearsal verdict from the eval's judge, when the build
  // checked rehearsals. A fail flags the case; it is still driven.
  rehearsal_score?: "pass" | "fail" | null
  rehearsal_reasoning?: string | null
}

// A case the save sends: the generated case plus the run it was driven in.
// The save mints no test case for a reviewed run, so this id is what keeps
// the golden answer key out of the test, train and val splits.
export type DrivenCaseWire = SyntheticUserCaseWire & { leaf_run_id: string }

// The generate_cases output, cached against exactly the inputs it depends
// on (the approved prompts, the spec text and the Data Guide — the run config
// plays no part in persona generation). A re-drive with all three unchanged
// reuses the cases
// instead of re-paying the multi-minute copilot generation, which makes the
// fix-config-then-drive-again recovery loop fast.
export type CachedSuCases = {
  prompts_json: string
  spec_text: string
  // The trimmed Data Guide the case writer read, "" for none. Older drafts
  // lack it and keep their cases whatever the guide is now: nothing on record
  // says which guide they were written under.
  data_guide?: string
  cases: SyntheticUserCaseWire[]
}

// The cached cases iff they were generated from EXACTLY this plan, spec and
// Data Guide (byte-compare); anything else means regenerate. Fresh variation on the
// same scenarios is deliberately not offered — that's what Refine Plan
// is for.
export function reusable_cached_cases(
  cache: CachedSuCases | null,
  approved_prompts: string[],
  spec: string,
  data_guide: string,
): SyntheticUserCaseWire[] | null {
  if (!cache || cache.cases.length === 0) return null
  if (cache.spec_text !== spec) return null
  if (cache.data_guide !== undefined && cache.data_guide !== data_guide) {
    return null
  }
  if (cache.prompts_json !== JSON.stringify(approved_prompts)) return null
  return cache.cases
}

// The plan's cases after grounding in an OpenEnv server, cached apart from
// the generated ones above. Grounding writes each case's specifics and judge
// guidance from what it found on the server, so this set also depends on the
// server, on the judge model the grounding agent ran on, and on the synthetic
// user guide it read. Keeping the generated cases separately means a grounding
// failure or a judge change re-grounds them without paying for generation
// again.
export type CachedGroundedCases = {
  prompts_json: string
  spec_text: string
  openenv_server_id: string
  // model_choice_key of the model the grounding agent ran on. Older drafts
  // keyed this on the judge model, under another name, and so ground again.
  grounding_model: string
  // The trimmed Data Guide the grounding agent read, "" for none. Missing on
  // older drafts, which ground again.
  data_guide?: string
  // The turn limit grounding was told: 1 for a one-message conversation, null
  // otherwise, since only that limit changes what grounding is told. Missing on
  // older drafts, which keep their sets.
  max_turns?: number | null
  // Who gave the cases' rehearsal verdicts (rehearsal_judge_key), null when
  // none was asked for. A verdict is shown only under that same judge. Missing
  // on older drafts, whose verdicts are then never shown.
  rehearsal_judge_key?: string | null
  cases: SyntheticUserCaseWire[]
  // How many cases grounding dropped. The drive counts them as planned-for,
  // not failed, so the shortfall it reports is only its own.
  grounding_dropped: number
  // The dropped cases themselves, which the review's notice lists, and
  // whether that notice has been closed. Both belong to this grounded set, so
  // a new plan or a new grounding starts them over.
  drops: GroundingDrop[]
  drops_notice_seen: boolean
}

// A grounded set as a stored draft holds it. Drafts written before drops were
// kept lack both keys and restore with no drops, so they show no notice.
export function restore_cached_grounded_cases(
  saved: Partial<CachedGroundedCases> | null | undefined,
): CachedGroundedCases | null {
  if (!saved || !Array.isArray(saved.cases)) return null
  return {
    ...(saved as CachedGroundedCases),
    drops: Array.isArray(saved.drops) ? saved.drops : [],
    drops_notice_seen: saved.drops_notice_seen === true,
  }
}

export type CaseGroundingKey = {
  openenv_server_id: string
  grounding_model: string
  data_guide: string
  // grounding_turn_limit of the drive's conversation length.
  max_turns: number | null
}

// The turn limit grounding is told for a conversation of `turns` replies: only
// a one-message conversation changes what grounding does, so any other length
// is sent and keyed as none, and changing it reuses the grounded set.
export function grounding_turn_limit(turns: number | null): number | null {
  return turns === 1 ? 1 : null
}

// The identity of the judge that grades rehearsals: its model, thinking level
// and prompt. Null when no rehearsal is judged.
export function rehearsal_judge_key(judge: JudgeConfig | null): string | null {
  if (!judge) return null
  return JSON.stringify([
    judge.model_name,
    judge.model_provider,
    judge.thinking_level ?? null,
    judge.prompt,
  ])
}

// The cases of a reused grounded set, with their rehearsal verdicts kept only
// when the same judge (rehearsal_judge_key) gave them; any other judge's
// verdicts are cleared, so the review never shows a verdict the current judge
// didn't give.
export function cases_with_current_verdicts(
  cache: CachedGroundedCases,
  judge_key: string | null,
): SyntheticUserCaseWire[] {
  if (judge_key !== null && (cache.rehearsal_judge_key ?? null) === judge_key) {
    return cache.cases
  }
  return cache.cases.map((c) =>
    c.rehearsal_score == null && c.rehearsal_reasoning == null
      ? c
      : { ...c, rehearsal_score: null, rehearsal_reasoning: null },
  )
}

// The cached grounded set iff it came from EXACTLY this plan and spec and was
// grounded in this server by this model under this Data Guide and turn limit.
// A set from an older draft has no turn limit on record and is kept.
export function reusable_grounded_cases(
  cache: CachedGroundedCases | null,
  approved_prompts: string[],
  spec: string,
  key: CaseGroundingKey,
): CachedGroundedCases | null {
  if (!cache || cache.cases.length === 0) return null
  if (cache.spec_text !== spec) return null
  if (cache.prompts_json !== JSON.stringify(approved_prompts)) return null
  if (cache.openenv_server_id !== key.openenv_server_id) return null
  if (cache.grounding_model !== key.grounding_model) return null
  if (cache.data_guide === undefined || cache.data_guide !== key.data_guide) {
    return null
  }
  if (cache.max_turns !== undefined && cache.max_turns !== key.max_turns) {
    return null
  }
  return cache
}

// A run config as a cache key: object keys sorted and the tool list ordered,
// so two configs that would generate the same data key the same however they
// were assembled. Every field of the config counts, because every field
// reaches the generation call.
export function run_config_cache_key(
  properties: KilnAgentRunConfigProperties,
): string {
  const ordered_tools = {
    ...properties,
    tools_config: {
      ...properties.tools_config,
      tools: [...(properties.tools_config?.tools ?? [])].sort(),
    },
  }
  return JSON.stringify(ordered_tools, (_key, value) =>
    value && typeof value === "object" && !Array.isArray(value)
      ? Object.fromEntries(
          Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
            a < b ? -1 : a > b ? 1 : 0,
          ),
        )
      : value,
  )
}

// The single-turn arm's minted test inputs, cached against exactly what
// produced them: the approved plan prompts, the whole run config the input
// generator ran under, and the grounding data-guide the mint ran under (the
// spec plays no part — it already shaped the PLAN). A re-run with all three
// unchanged reuses the inputs instead of re-paying one generation call per
// prompt, which makes the fix-config-then-run-again recovery loop fast.
export type CachedMintedInputs = {
  prompts_json: string
  // The grounding guide passed to the mint (null = ungrounded). Older drafts
  // lack the key and simply miss the cache.
  data_guide?: string | null
  // run_config_cache_key of the config the mint ran under. Model, tools,
  // skills and sampling all change what gets written, so the key is the whole
  // config rather than a few fields of it. Older drafts lack the key and miss
  // the cache, which re-mints rather than serving inputs we can't describe.
  run_config_json?: string
  // Each input as the string the pipeline runs on (structured-task inputs
  // are JSON strings — the same encoding the saved eval's items store).
  inputs: string[]
}

export function reusable_minted_inputs(
  cache: CachedMintedInputs | null,
  approved_prompts: string[],
  data_guide: string | null,
  run_config_json: string,
): string[] | null {
  if (!cache || cache.inputs.length === 0) return null
  if ((cache.data_guide ?? null) !== data_guide) return null
  if (cache.run_config_json !== run_config_json) return null
  if (cache.prompts_json !== JSON.stringify(approved_prompts)) return null
  return cache.inputs
}

// Whether the clarify questions still fit the text the caller pairs them
// against: source is a snapshot of the exact text they were generated from,
// byte-compared because the copilot saw that raw string. Null means no set
// has landed, so regenerate.
export function questions_are_current(
  source: string | null,
  paired_against: string,
): boolean {
  return source !== null && source === paired_against
}

// Whether a suggested eval name may be written into the name field. A name
// the user typed is never overwritten; an untouched field is always safe to
// fill. Untouched means either empty/whitespace-only (nothing to lose, and a
// stray space is not a typed name) or still byte-equal to prefilled_name, the
// name the MACHINE last wrote — that one tracks the model's latest suggestion,
// so rewriting the description and continuing again renames the eval after the
// new one. Raw byte compare: a trailing space is a real edit.
export function should_prefill_suggested_name(
  current_name: string,
  prefilled_name: string | null,
): boolean {
  return current_name.trim() === "" || current_name === prefilled_name
}

// Whether a failed refine may discard the refine form's current values.
// Content the user may have edited is never discarded (current must still be
// byte-equal to what the code last wrote); programmatic content is discarded
// only when the source values it was derived from have changed underneath
// it. A transient failure with an unchanged source therefore keeps the good
// refinement, and a null snapshot (values restored from a saved draft, where
// authorship is unknowable) always means keep.
// The byte-compares rely on callers snapshotting the object they just built
// with the same construction on both sides, not on JSON canonicalization.
export function should_invalidate_refined_values(
  current: Record<string, string | null>,
  programmatic_json: string | null,
  derived_from_json: string | null,
  current_source_json: string,
): boolean {
  return (
    programmatic_json !== null &&
    JSON.stringify(current) === programmatic_json &&
    derived_from_json !== current_source_json
  )
}

export type BuilderDraft = {
  // Step 1-3 — spec authoring.
  description: string
  // Which text the last Continue processed. The clarify gate pairs questions
  // to this, so a reload must not swap the pairing target to an un-Continued
  // edit; drafts written before this key restore it as null.
  continued_description: string | null
  name: string
  // Which name the machine last wrote, so a reload keeps a still-untouched
  // suggestion replaceable; drafts from before this key restore null, which
  // safely treats the restored name as the user's own. Deliberately unlike
  // refined_values_programmatic_json, whose snapshot is NOT persisted so refine
  // text always restores as user-owned: discarding that text destroys content,
  // while a name suggestion is cheap to replace.
  prefilled_name: string | null
  property_values: Record<string, string | null>
  refined_property_values: Record<string, string | null>
  suggested_edits: Record<string, SuggestedEdit>
  // Step 4 — the dataset size the user chose, and what the save deals by.
  // Null on drafts written before the picker existed; they restore as Standard.
  batch_size: BatchSize | null
  // Step 4 — the approved plan (minutes of copilot work to recreate).
  batch_plan: { prompts: string[]; summary: string } | null
  batch_plan_edited: boolean
  // The plan's generated synthetic users (more minutes) — reused on drive
  // while plan+spec are byte-unchanged, revalidated in reusable_cached_cases.
  cached_su_cases: CachedSuCases | null
  // The plan's grounded cases on an OpenEnv build, revalidated in
  // reusable_grounded_cases. Null on older drafts.
  cached_grounded_cases: CachedGroundedCases | null
  // The single-turn arm's minted inputs — reused on a re-run while
  // plan+model are byte-unchanged, revalidated in reusable_minted_inputs.
  cached_minted_inputs: CachedMintedInputs | null
  // The auto-picked task sample grounding single-turn planning and input
  // minting — persisted beside the plan it grounded, so a restored session
  // mints with the same grounding (and saves the same provenance record).
  grounding_sample: { input: string; output: string } | null
  // The task's saved Data Guide as it last read (null when the task had none,
  // or the first read failed), and whether the user keeps it in the requests.
  // Every plan and drive reads the guide again before using it, so this copy
  // is what a restored session shows until then, and what it keeps if that
  // read fails. Drafts written before guides were read here restore as no
  // guide, off.
  data_guide_text: string | null
  use_data_guide: boolean
  // The user chose Continue Without Data Guide on this draft: Step 4 plans
  // without offering one again, on this session and on a reload.
  data_guide_skipped: boolean
  // The offer was on screen when the draft was last written: Step 4 had
  // been reached and was waiting on the user's choice, with no plan yet.
  // A restore lands such a draft back on Step 4, where the guide is read
  // again (the user may have just saved one) and the flow resumes. Every
  // other draft without a plan restores no further than the refine step,
  // as before.
  data_guide_offer_pending: boolean
  // Batch-tag bookkeeping — a CORRECTNESS carry, not convenience: these
  // name runs already on disk. The per-arm live-batch tag plus
  // undeleted_batch_tags, the delete-on-next-drive cleanup list (shared —
  // a task is one arm, so its tags never mix).
  multi_turn_batch_tag: string | null
  single_turn_batch_tag: string | null
  undeleted_batch_tags: string[]
  // The Drive Settings model lanes. Persisted so a reload or the
  // connect-a-provider round trip keeps the user's picks; pre-Drive-Settings
  // drafts restore these as null (?? below) and fall back to pre-population.
  su_driver: ModelChoice | null
  input_generator: ModelChoice | null
  // The whole run config the input generator was last committed with: model,
  // tools, skills and sampling. Kept beside the model lane because every part
  // of it changes what gets written, and because a restored session must be
  // able to run again without reopening Generation Settings. Drafts written
  // before the input lane carried a config restore this as null, which reads
  // as "nothing chosen".
  input_gen_run_config: KilnAgentRunConfigProperties | null
  judge_model: ModelChoice | null
  // The judge's thinking level from Generation Settings. Null runs the judge at
  // its model's default; drafts written before this key restore that way.
  judge_thinking_level: string | null
  // The model the grounding agent runs on (OpenEnv builds), and its thinking
  // level. Null on drafts written before the lane existed: the dialog then
  // starts it on the judge model.
  grounding_model?: ModelChoice | null
  grounding_thinking_level?: string | null
  // Generation Settings' Check Rehearsals box (OpenEnv builds): whether
  // grounding asks the judge to grade each case's rehearsal. Missing on older
  // drafts, which restore it off.
  check_rehearsals?: boolean
  // The Generation Settings conversation length (multi-turn). Persisted for
  // the same reason as the lanes above: a reload should not silently put the
  // drive back on the default length. Null means no choice on record — drafts
  // written before this key restore that way — and the page falls back to its
  // default turn count.
  turns_per_case: number | null
  // The Generation Settings box that preceded the task's Data Guide (who
  // talks to the agent). Only older drafts have it; restore_synthetic_user_guide
  // reads it to start the Data Guide dialog with that text.
  synthetic_user_guide?: string
  // The run config the entry page chose for this eval. Persisted so a reload
  // keeps evaluating the same thing; drafts written before the entry page
  // asked restore this as null, which reads as "nothing chosen" and leaves
  // the task default in charge.
  target_run_config_id: string | null
  // The OpenEnv server the target run config's tools reach (multi-turn), and
  // the tool set it was looked up for: a run config whose tools change is
  // looked up again. Null when no lookup is on record, including on older
  // drafts.
  openenv_server_lookup: OpenEnvServerLookup | null
  // The Refine Plan steer the plan on screen was drafted under. A Refine Plan
  // opened because cases dropped starts from it, so it has to survive a
  // reload too.
  landed_plan_steer: string
}

export type OpenEnvServerLookup = {
  tool_ids_key: string
  openenv_server_id: string | null
}

export type CachedResetArgumentsBrief = {
  openenv_server_id: string
  brief: string | null
}

export const EMPTY_BUILDER_DRAFT: BuilderDraft = {
  description: "",
  continued_description: null,
  name: "",
  prefilled_name: null,
  property_values: {},
  refined_property_values: {},
  suggested_edits: {},
  batch_size: null,
  batch_plan: null,
  batch_plan_edited: false,
  cached_su_cases: null,
  cached_grounded_cases: null,
  cached_minted_inputs: null,
  grounding_sample: null,
  data_guide_text: null,
  use_data_guide: false,
  data_guide_skipped: false,
  data_guide_offer_pending: false,
  multi_turn_batch_tag: null,
  single_turn_batch_tag: null,
  undeleted_batch_tags: [],
  su_driver: null,
  input_generator: null,
  input_gen_run_config: null,
  judge_model: null,
  judge_thinking_level: null,
  turns_per_case: null,
  grounding_model: null,
  grounding_thinking_level: null,
  target_run_config_id: null,
  openenv_server_lookup: null,
  landed_plan_steer: "",
}

export function restore_synthetic_user_guide(saved: unknown): string {
  return typeof saved === "string" ? saved : ""
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
    draft.single_turn_batch_tag !== null ||
    draft.undeleted_batch_tags.length > 0
  )
}

// Whether a stored draft has authoring work to resume: the spec fields or a
// plan. Batch tags alone do not count here, unlike draft_has_content: a Reset
// keeps them for cleanup, and a draft that is only cleanup bookkeeping is
// nothing to continue. Drives the Evals page's button and the builder's
// Reset, both of which speak to the user about their work.
export function draft_is_resumable(draft: BuilderDraft): boolean {
  return (
    draft.description.trim() !== "" ||
    draft.name.trim() !== "" ||
    record_has_content(draft.property_values) ||
    record_has_content(draft.refined_property_values) ||
    Object.keys(draft.suggested_edits).length > 0 ||
    draft.batch_plan !== null
  )
}

// The furthest SAFE step a restored draft can land on — never past the plan
// screen (step 4), and never into review: review state isn't persisted, and
// presenting stale results would be worse than replaying a drive.
//   - a plan exists → the plan screen ("generate")
//   - the Data Guide offer was open → the plan screen, where the offer
//     re-opens (or, once a guide exists, the plan fires under it)
//   - refine output exists → "refine" (clarify Q&A isn't persisted, so a
//     draft that died mid-clarify restarts from the description)
//   - otherwise → "describe" with the description prefilled
export type RestoreStep = "describe" | "refine" | "generate"

export function restore_step(draft: BuilderDraft): RestoreStep {
  if (draft.batch_plan !== null && draft.batch_plan.prompts.length > 0) {
    return "generate"
  }
  if (draft.data_guide_offer_pending) {
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
// the tags: they name runs already on disk, and delete-on-next-drive is
// the only thing that ever cleans those up — a full wipe would orphan them
// forever (the leak the draft's tag persistence exists to prevent).
export function reset_draft_keeping_tags(draft: BuilderDraft): BuilderDraft {
  return {
    ...EMPTY_BUILDER_DRAFT,
    multi_turn_batch_tag: draft.multi_turn_batch_tag,
    single_turn_batch_tag: draft.single_turn_batch_tag,
    undeleted_batch_tags: draft.undeleted_batch_tags,
  }
}

// After a multi-turn save, the just-saved batch's chains ARE the eval's data
// — never delete them. Earlier aborted drives can still have left superseded
// chains on disk (undeleted_batch_tags); wiping the whole draft would orphan
// those forever, since delete-on-next-drive is their only cleanup. Carry ONLY
// those leftover tags — with the saved batch's own tag excluded — into an
// otherwise-empty draft, so a later drive on this task cleans them up. The
// saved batch is dropped from both tag slots so no future replace_batch_tags
// can delete the eval's chains.
export function draft_after_save_keeping_stranded_tags(
  saved_batch_tag: string,
  undeleted_batch_tags: string[],
): BuilderDraft {
  return {
    ...EMPTY_BUILDER_DRAFT,
    undeleted_batch_tags: undeleted_batch_tags.filter(
      (tag) => tag !== saved_batch_tag,
    ),
  }
}

// The Evals page's create button advertises a resumable draft (the silent
// restore already happens on builder entry; this makes it discoverable).
export function create_eval_button_label(has_draft: boolean): string {
  return has_draft ? "Continue Eval Draft" : "Create Eval"
}

// Where that button goes. A draft continues in the builder, which restores it
// on entry and, if Copilot is not connected there, shows its own connect card
// with the draft kept; everything else starts on the Create Eval page. Kept
// beside the label so the two cannot promise different things.
export function create_eval_destination(
  has_draft: boolean,
): "builder" | "select_template" {
  return has_draft ? "builder" : "select_template"
}
