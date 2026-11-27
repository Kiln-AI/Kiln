// The eval check panel's numbers: what a judged batch says about the eval
// itself, shown on the review start screen before the owner reviews a sample.
// Everything here is arithmetic over the batch already in memory, except
// load_failure_grouping, the one model call that sorts failures by cause,
// which only the owner starts.

import { get, writable, type Readable } from "svelte/store"
import { client } from "$lib/api_client"
import type { components } from "$lib/api_schema"
import type { JudgeConfig } from "$lib/eval/default_judge"
import type { OpenEnvReset, TraceMessage } from "$lib/types"
import { server_message } from "$lib/utils/error_handlers"
import type { GroundingDrop } from "./batch_plan_guidance"
import type { CachedGroundedCases } from "./builder_draft"
import type { TraceClaims } from "./claim_evidence"

export type GroupFailuresRequest =
  components["schemas"]["GroupFailuresApiInput"]
export type FailureGrouping = components["schemas"]["GroupFailuresApiOutput"]
export type FailureGroup = components["schemas"]["FailureGroupApi"]
export type FaultKind = FailureGroup["fault_kind"]

// The parts of a judged case the panel reads.
export type PanelCase = Pick<
  TraceClaims,
  | "trace_id"
  | "judge_score"
  | "judge_reasoning"
  | "raw_input"
  | "raw_output"
  | "trace"
  | "openenv_reset"
  | "judge_guidance"
  | "rehearsal_score"
  | "rehearsal_reasoning"
>

// ── Headroom ──────────────────────────────────────────────────────────────

// At or above this pass rate the baseline already passes nearly everything,
// so the eval cannot show an improvement.
export const TOO_EASY_PASS_RATE = 0.85
// At or below this pass rate some cases may be impossible for any agent.
export const TOO_HARD_PASS_RATE = 0.1

export type HeadroomVerdict = "too_easy" | "too_hard" | "ok"

export type Headroom = {
  passed: number
  total: number
  rate: number
  verdict: HeadroomVerdict
}

export function headroom(cases: Pick<PanelCase, "judge_score">[]): Headroom {
  const total = cases.length
  const passed = cases.filter((c) => c.judge_score === "pass").length
  const rate = total > 0 ? passed / total : 0
  let verdict: HeadroomVerdict = "ok"
  if (total > 0 && rate >= TOO_EASY_PASS_RATE) verdict = "too_easy"
  else if (total > 0 && rate <= TOO_HARD_PASS_RATE) verdict = "too_hard"
  return { passed, total, rate, verdict }
}

// Rounded from the counts, so 23 of 40 reads 58%, not 57% from 0.575 * 100.
export function percent(part: number, whole: number): string {
  return `${whole > 0 ? Math.round((part * 100) / whole) : 0}%`
}

export function headroom_text(h: Headroom): string {
  if (h.verdict === "too_easy") {
    return `Too easy: ${percent(h.passed, h.total)} of the baseline's cases pass. At ${percent(TOO_EASY_PASS_RATE, 1)} or more, the eval can't show that a change made the agent better.`
  }
  if (h.verdict === "too_hard") {
    return `Check for cases no agent can pass: only ${percent(h.passed, h.total)} of the baseline's cases pass.`
  }
  return `${percent(h.passed, h.total)} of the baseline's cases pass, so the eval has room to show a change.`
}

// ── Cases per starting state ──────────────────────────────────────────────

export type FixtureCount = { fixture: string; count: number }

export type FixtureSpread = {
  rows: FixtureCount[]
  total: number
  // The starting state that holds more than half of the cases, if one does.
  crowded: FixtureCount | null
}

// A case's starting state, read from its reset arguments without the seed.
// Each OpenEnv server names its arguments its own way, so a single argument
// shows as its value and several show as name=value pairs.
export function fixture_label(reset: OpenEnvReset | null | undefined): string {
  const { seed: _seed, ...rest } = reset?.reset_kwargs ?? {}
  const keys = Object.keys(rest).sort()
  if (keys.length === 0) return "Default reset"
  const shown = (value: unknown) =>
    typeof value === "string" ? value : JSON.stringify(value)
  if (keys.length === 1) return shown(rest[keys[0]])
  return keys.map((key) => `${key}=${shown(rest[key])}`).join(", ")
}

// Null when no case ran in an OpenEnv server.
export function cases_per_fixture(
  cases: Pick<PanelCase, "openenv_reset">[],
): FixtureSpread | null {
  const grounded = cases.filter((c) => c.openenv_reset)
  if (grounded.length === 0) return null
  const counts = new Map<string, number>()
  for (const c of grounded) {
    const label = fixture_label(c.openenv_reset)
    counts.set(label, (counts.get(label) ?? 0) + 1)
  }
  const rows = [...counts.entries()]
    .map(([fixture, count]) => ({ fixture, count }))
    .sort((a, b) => b.count - a.count || a.fixture.localeCompare(b.fixture))
  const total = grounded.length
  const crowded = rows[0].count * 2 > total ? rows[0] : null
  return { rows, total, crowded }
}

// ── Rehearsal check ───────────────────────────────────────────────────────

// The judged cases whose rehearsal the judge also graded, and those it
// failed. A failed rehearsal means the case, its judge guidance or the judge
// is wrong. Null while no case carries a rehearsal verdict.
export type RehearsalCheck = {
  judged: number
  failed: Pick<PanelCase, "trace_id" | "raw_input" | "rehearsal_reasoning">[]
}

export function rehearsal_check(
  cases: Pick<
    PanelCase,
    "trace_id" | "raw_input" | "rehearsal_score" | "rehearsal_reasoning"
  >[],
): RehearsalCheck | null {
  const judged = cases.filter(
    (c) => c.rehearsal_score === "pass" || c.rehearsal_score === "fail",
  )
  if (judged.length === 0) return null
  return {
    judged: judged.length,
    failed: judged.filter((c) => c.rehearsal_score === "fail"),
  }
}

// ── Reasoning and drops ───────────────────────────────────────────────────

// run_judge_for_trace (studio_server eval_builder_utils.py) writes this
// sentence in place of reasoning when the judge returned none.
const NO_REASONING_PLACEHOLDER =
  /^The judge returned a (PASS|FAIL) verdict without an explicit reasoning trace\.$/

export function has_judge_reasoning(reasoning: string): boolean {
  const text = reasoning.trim()
  return text.length > 0 && !NO_REASONING_PLACEHOLDER.test(text)
}

// Failed cases the grouping cannot read, because the judge gave no reasoning.
export function failures_without_reasoning(
  cases: Pick<PanelCase, "judge_score" | "judge_reasoning">[],
): number {
  return cases.filter(
    (c) => c.judge_score === "fail" && !has_judge_reasoning(c.judge_reasoning),
  ).length
}

// The drops of the grounded set the batch was driven from; none when the
// cached set belongs to another plan.
export function batch_drops(
  cache: CachedGroundedCases | null,
  driven_prompts_json: string | null,
): GroundingDrop[] {
  if (!cache || driven_prompts_json === null) return []
  return cache.prompts_json === driven_prompts_json ? cache.drops : []
}

// Plain words for the drop reasons in eval_grounding/models.py (DropReason).
// A drop with no reason was saved before reasons were kept; those were all
// "didn't fit".
const DROP_REASON_LABELS: Record<string, string> = {
  no_fit: "didn't fit the environment",
  unrepresentable: "needed something the environment can't hold",
  rehearsal_failed: "rehearsal failed",
  limit: "ran out of calls or time",
  invalid_output: "unusable result",
}

export type DropCount = { label: string; count: number }

export function drops_by_reason(drops: GroundingDrop[]): DropCount[] {
  const counts = new Map<string, number>()
  for (const drop of drops) {
    const reason = drop.drop_reason ?? "no_fit"
    const label = DROP_REASON_LABELS[reason] ?? reason
    counts.set(label, (counts.get(label) ?? 0) + 1)
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
}

// ── Failure grouping (one model call) ─────────────────────────────────────

// Mirrors MAX_GROUPED_FAILURES in eval_builder_models.py.
export const MAX_GROUPED_FAILURES = 100
const MAX_REASONING_CHARS = 4000
const MAX_EXCERPT_CHARS = 600
const MAX_GUIDANCE_CHARS = 2000

// Cuts the middle out of a long text: a judge's reasoning tends to open with
// what it checked and close with its verdict, and both matter.
export function clip(text: string, max: number): string {
  if (text.length <= max) return text
  const half = Math.floor((max - 5) / 2)
  return `${text.slice(0, half)} […] ${text.slice(text.length - half)}`
}

function message_text(message: TraceMessage | undefined): string {
  const content = message && "content" in message ? message.content : null
  if (typeof content === "string") return content
  if (!Array.isArray(content)) return ""
  return content
    .map((part) => ("text" in part ? part.text : ""))
    .filter(Boolean)
    .join("\n")
}

// The case's first message and final reply, short enough to send for every
// failure. Falls back to the raw input and output when there is no trace.
export function case_excerpt(
  c: Pick<PanelCase, "trace" | "raw_input" | "raw_output">,
): string {
  const trace = c.trace ?? []
  const first = message_text(trace.find((m) => m.role === "user"))
  const last = message_text(
    [...trace].reverse().find((m) => m.role === "assistant" && m.content),
  )
  return [
    `First message: ${clip(first || c.raw_input, MAX_EXCERPT_CHARS)}`,
    `Final reply: ${clip(last || c.raw_output, MAX_EXCERPT_CHARS)}`,
  ].join("\n")
}

// The grouping request for a batch, or null when no failure has reasoning to
// group (an all-pass batch, or a judge that wrote none).
export function failure_grouping_request(
  cases: PanelCase[],
  spec_text: string,
  judge: JudgeConfig,
): GroupFailuresRequest | null {
  const failures = cases
    .filter(
      (c) => c.judge_score === "fail" && has_judge_reasoning(c.judge_reasoning),
    )
    .slice(0, MAX_GROUPED_FAILURES)
    .map((c) => ({
      case_id: c.trace_id,
      judge_reasoning: clip(c.judge_reasoning, MAX_REASONING_CHARS),
      case_summary: case_excerpt(c),
      judge_guidance: c.judge_guidance
        ? clip(c.judge_guidance, MAX_GUIDANCE_CHARS)
        : null,
    }))
  if (failures.length === 0) return null
  return { spec_text, judge, failures }
}

// Which batch a grouping describes: the verdicts, the spec text they were
// judged against, and the calibration round. A re-drive, a refine round or a
// rebuild changes it.
export function eval_check_key(
  cases: Pick<PanelCase, "trace_id" | "judge_score">[],
  reviewed_spec_text: string,
  calibration_round: number,
): string {
  const verdicts = cases.map((c) => `${c.trace_id}:${c.judge_score}`).join("|")
  return JSON.stringify([calibration_round, reviewed_spec_text, verdicts])
}

export type FailureGroupingState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; grouping: FailureGrouping }
  | { status: "unavailable"; message: string }

// Never throws: any failure becomes "unavailable", so the panel degrades
// and the review goes on.
export async function load_failure_grouping(
  project_id: string,
  task_id: string,
  body: GroupFailuresRequest,
): Promise<FailureGroupingState> {
  try {
    const { data, error } = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/eval_builder/group_failures",
      { params: { path: { project_id, task_id } }, body },
    )
    if (error || !data) {
      return {
        status: "unavailable",
        message: server_message(error) ?? "The grouping request failed.",
      }
    }
    return { status: "ready", grouping: data }
  } catch (e) {
    return {
      status: "unavailable",
      message: server_message(e) ?? "Couldn't reach the server.",
    }
  }
}

export type EvalCheckState = {
  key: string | null
  grouping: FailureGroupingState
  answers: OwnerAnswers
}

export type EvalCheckStore = Readable<EvalCheckState> & {
  set_batch: (key: string) => void
  group: (
    project_id: string,
    task_id: string,
    request: GroupFailuresRequest | null,
  ) => Promise<void>
  leave: () => void
  set_answers: (answers: OwnerAnswers) => void
}

// The panel's state for the batch on screen: the grouping and the owner's
// answers, both cleared by a new batch and both kept when the panel leaves
// the screen. The grouping is paid, so it starts only from group(), which
// the owner's button calls. A grouping that resolves after the batch
// changed, or after the owner left the screen, is dropped.
export function eval_check_store(
  load: typeof load_failure_grouping = load_failure_grouping,
): EvalCheckStore {
  const state = writable<EvalCheckState>({
    key: null,
    grouping: { status: "idle" },
    answers: {},
  })
  // Bumped by every call, batch change and leave: only the latest call lands.
  let generation = 0
  const set_grouping = (grouping: FailureGroupingState) =>
    state.update((s) => ({ ...s, grouping }))

  return {
    subscribe: state.subscribe,
    set_batch(key) {
      if (get(state).key === key) return
      generation++
      state.set({ key, grouping: { status: "idle" }, answers: {} })
    },
    async group(project_id, task_id, request) {
      const call = ++generation
      if (request === null) {
        set_grouping({
          status: "unavailable",
          message: "There are no failures with judge reasoning to sort.",
        })
        return
      }
      set_grouping({ status: "loading" })
      const result = await load(project_id, task_id, request)
      if (call === generation) set_grouping(result)
    },
    leave() {
      generation++
      if (get(state).grouping.status === "loading") {
        set_grouping({ status: "idle" })
      }
    },
    set_answers(answers) {
      state.update((s) => ({ ...s, answers }))
    },
  }
}

// What the grouping button offers, before the owner pays for it: how many
// failures it sorts, and what it reads.
export function grouping_offer_text(failed: number, groupable: number): string {
  const sent = Math.min(groupable, MAX_GROUPED_FAILURES)
  const cap =
    groupable > MAX_GROUPED_FAILURES
      ? ` One call takes at most ${MAX_GROUPED_FAILURES}: the first ${MAX_GROUPED_FAILURES} in batch order.`
      : ""
  return `Sort ${sent} of ${failed} failures by cause with one call to the judge's model.${cap} ${GROUPING_READS}`
}

// What a finished grouping covered.
export function grouping_scope_text(
  grouping: FailureGrouping,
  failed: number,
): string {
  const shortened = grouping.texts_shortened
    ? " Long texts were shortened to fit one call."
    : ""
  return `Grouped ${grouping.failure_count} of ${failed} failures. ${GROUPING_READS}${shortened}`
}

const GROUPING_READS =
  "It reads the judge's own reasoning and a short excerpt of each case (first message and final reply), so it can miss a fault in the judge itself."

// ── Reading the grouping ──────────────────────────────────────────────────

export const FAULT_KIND_LABELS: Record<FaultKind, string> = {
  agent: "Agent",
  reference: "Reference",
  judge: "Judge",
  world: "World",
  simulated_user: "Simulated user",
  unknown: "Unknown",
}

export type FaultCount = { kind: FaultKind; label: string; count: number }

// Every fault kind with its count, in a fixed order. Unknown shows only when
// some failure is unknown.
export function fault_counts(grouping: FailureGrouping): FaultCount[] {
  const kinds = Object.keys(FAULT_KIND_LABELS) as FaultKind[]
  return kinds
    .map((kind) => ({
      kind,
      label: FAULT_KIND_LABELS[kind],
      count: grouping.failures.filter((f) => f.fault_kind === kind).length,
    }))
    .filter((row) => row.kind !== "unknown" || row.count > 0)
}

// Counts only agent failures in a group about the spec's rule.
export function is_on_target(group: FailureGroup): boolean {
  return group.fault_kind === "agent" && group.about_rule
}

export function on_target_sentence(grouping: FailureGrouping): string {
  const n = grouping.failure_count
  const head = `${grouping.on_target_count} of ${n} grouped ${n === 1 ? "failure is" : "failures are"} about "${grouping.rule_summary}".`
  const other = grouping.groups.find((g) => !is_on_target(g))
  if (!other) return head
  return `${head} ${other.count} ${other.count === 1 ? "is" : "are"} about "${other.name}", the largest other group.`
}

// What the panel's question names as the eval's purpose: the grouping's
// short restatement of the spec, or the spec's opening when there is none.
export function rule_label(
  spec_text: string,
  state: FailureGroupingState,
): string {
  const source =
    state.status === "ready"
      ? state.grouping.rule_summary
      : spec_text.trim().split("\n")[0] ?? ""
  // The panel ends the sentence itself.
  const text = source.replace(/[.\s]+$/, "")
  return text.length > 160 ? `${text.slice(0, 157)}...` : text
}

// ── The owner's answers ───────────────────────────────────────────────────

export type OwnerAnswer =
  | "in_scope"
  | "out_of_scope"
  | "should_be_harder"
  | "reference_is_wrong"

export const OWNER_ANSWERS: { value: OwnerAnswer; label: string }[] = [
  { value: "in_scope", label: "In Scope" },
  { value: "out_of_scope", label: "Out of Scope" },
  { value: "should_be_harder", label: "Should Be Harder" },
  { value: "reference_is_wrong", label: "Reference Is Wrong" },
]

// The row key for the whole eval, which no group name can take.
export const WHOLE_EVAL_KEY = ""

// The owner's answer per question row: WHOLE_EVAL_KEY, or a group's name.
export type OwnerAnswers = Record<string, OwnerAnswer>

export type QuestionRow = { key: string; label: string }

// One row for the whole eval, then one per cause group when the grouping is
// ready.
export function question_rows(
  h: Headroom,
  state: FailureGroupingState,
): QuestionRow[] {
  const rows: QuestionRow[] = [
    {
      key: WHOLE_EVAL_KEY,
      label: `The whole eval (${percent(h.passed, h.total)} pass)`,
    },
  ]
  if (state.status !== "ready") return rows
  return [
    ...rows,
    ...state.grouping.groups.map((g) => ({
      key: g.name,
      label: `${g.name} (${g.count})`,
    })),
  ]
}

// One line for the answers given so far, the whole eval first; null with
// none.
export function answers_summary(answers: OwnerAnswers): string | null {
  const keys = Object.keys(answers).sort(
    (a, b) => Number(b === WHOLE_EVAL_KEY) - Number(a === WHOLE_EVAL_KEY),
  )
  if (keys.length === 0) return null
  const label = (answer: OwnerAnswer) =>
    OWNER_ANSWERS.find((o) => o.value === answer)?.label ?? answer
  const parts = keys.map(
    (key) =>
      `${key === WHOLE_EVAL_KEY ? "the whole eval" : key}: ${label(answers[key])}`,
  )
  return `Your answers on the eval check: ${parts.join("; ")}.`
}
