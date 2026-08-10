// Claim/Evidence review — client mirror of the kiln_server buildClaimEvidence
// task contract. Hand-mirrored because the task lives outside this repo's
// generated API schema.
//
// The server task is PER-TRACE: one call distills one trace (raw_input +
// raw_output) plus the judge's decision into atomic claim/evidence pairs plus
// ONE top-level final judgement. The reviewer agrees/disagrees with each
// without reading the whole trace. The UI holds N of these (one per generated
// trace) and manages trace identity itself, since the server output carries
// no id.

import type { components } from "$lib/api_schema"
import type { TraceMessage } from "$lib/types"

export type CitationSource = "input" | "output"

// The verdict an AGREE on a claim supports. On the final judgement this
// always equals the judge's verdict (the server pins it deterministically);
// on other claims it's a direction bit — claims pointing opposite the judge
// are counter-evidence for catching a wrong judge.
export type ExpectedResult = "pass" | "fail"

// A start+end anchor into raw_input/raw_output. The parser highlights the span
// from the first occurrence of `from` through the end of `to`. Snippets (not
// long quotes) keep the model fast — it doesn't recite verbatim text.
export type Citation = {
  marker: number // the [n] referenced inline in evidence
  source: CitationSource
  from: string
  to: string
}

export type Claim = {
  claim: string
  expected_result: ExpectedResult
  // One sentence with inline [n] markers; counter-points folded into a
  // "…, though …" clause. Markers resolve via `citations`.
  evidence: string
  citations: Citation[]
}

// The one overall verdict entry — top-level, no longer a claim in the list.
// Structurally identical to Claim; kept as an alias so call sites read right.
export type FinalJudgement = Claim

// What buildClaimEvidence returns for a single trace. `claims` may be EMPTY
// (trivial single-property evals) — the final judgement always exists.
export type BuildClaimEvidenceOutput = {
  claims: Claim[]
  final_judgement: FinalJudgement
}

// What buildClaimEvidence takes for a single trace.
export type BuildClaimEvidenceInput = {
  raw_input: string
  raw_output: string
  eval_rubric: string
  judge_reasoning: string
  judge_score: ExpectedResult
}

// ── Client-side per-trace bundle ─────────────────────────────────────────

// Claims build lazily for multi-turn traces (the pipeline stream stops at
// the judge): "unbuilt" until the trace is selected/opened, then a
// build_claims round trip moves it through "building" to "built" or "error".
// Single-turn traces arrive "built" (review_traces builds claims eagerly).
export type ClaimsBuildState = "unbuilt" | "building" | "built" | "error"

// One generated trace + the claims built for it. raw_input/raw_output are kept
// client-side so the trace modal can render them and resolve citation spans.
// leaf_run_id is the durable TaskRun identity for multi-turn chains (from
// run_cases_batch) — the save path writes the golden rating onto it; null for
// single-turn traces (their TaskRuns are created at save time).
// claims/final_judgement are null until claims_state is "built".
export type TraceClaims = {
  trace_id: string
  leaf_run_id: string | null
  raw_input: string
  raw_output: string
  judge_score: ExpectedResult
  judge_reasoning: string
  claims: Claim[] | null
  final_judgement: FinalJudgement | null
  claims_state: ClaimsBuildState
  claims_error: string | null
  // The structured conversation the judge saw (multi-turn only). raw_output is
  // its lossy flattening; the trace modal renders THIS in the house chat UI and
  // remaps output-source citation spans back onto it. Absent/null for
  // single-turn traces and legacy data — the modal then keeps the raw view.
  trace?: TraceMessage[] | null
}

// ── Human review (UI output) ─────────────────────────────────────────────

// Server claims carry no id, so verdicts are positional (index into
// TraceClaims.claims). The final judgement gets its own slot.
export type ClaimVerdict = {
  agrees: boolean | null // null = not yet reviewed
  why: string // required when the human disagrees — feeds the refine loop
}

export type TraceReview = {
  trace_id: string
  claim_verdicts: ClaimVerdict[]
  final_judgement_verdict: ClaimVerdict
}

// ── Citation resolution ──────────────────────────────────────────────────

// Resolve a citation to a [start, end) span in its source text. Finds the
// first occurrence of `from`, then the first `to` at/after it (so `to` can sit
// later in the text; equal to `from` for a short span). Returns null if either
// anchor is absent — the UI then shows the citation without a highlight rather
// than highlighting the wrong place.
//
// Grep-safety note (open question): for repeated identical `from`
// snippets this anchors to the FIRST match, which can mis-locate. Mitigation is
// on the model side (pick a `from` long enough to be locally unique); a future
// optional occurrence index could disambiguate if it proves necessary.
export function resolve_citation_span(
  text: string,
  citation: Pick<Citation, "from" | "to">,
): { start: number; end: number } | null {
  const start = text.indexOf(citation.from)
  if (start < 0) return null
  const to_at = text.indexOf(citation.to, start)
  if (to_at < 0) return null
  return { start, end: to_at + citation.to.length }
}

// ── Structured-trace span mapping ────────────────────────────────────────
//
// The trace modal renders the structured conversation (TraceMessage[]) in the
// house chat UI, but citations resolve against raw_output — the server's
// FLATTENED rendering of that trace. This maps a resolved [start, end) span in
// raw_output back onto the trace: which message, which block kind, and the
// offset within that block's text, so the chat UI can highlight the exact node.
//
// It works by re-computing the server flattener's block layout in TS. The port
// mirrors libs/core .../eval_trace_formatter.py EXACTLY — the same per-message
// block precedence (its lossy rule: content overwrites reasoning/tool blocks so
// only ONE block is emitted per message), the same tool-call formatting, the
// same tool-result .output unwrapping, and the same "\n\n" join keyed on the
// raw trace index. Any drift would shift offsets, so the mapper verifies the
// recomputed block against raw_output before trusting it (see below).

export type TraceHighlightKind =
  | "content"
  | "reasoning"
  | "tool_calls"
  | "tool_result"

export type TraceHighlight = {
  trace_index: number
  kind: TraceHighlightKind
  start: number
  end: number
}

// One emitted flattener block with its absolute span in the recomputed string.
type FlattenedBlock = {
  trace_index: number
  kind: TraceHighlightKind
  content_start: number
  content_end: number
  content: string
}

// Empty strings are falsy in Python's `if content:`, so a message whose block
// text is empty emits nothing — mirror that with JS truthiness throughout.
function trace_role(message: TraceMessage): string {
  return "role" in message && typeof message.role === "string"
    ? message.role
    : ""
}

// Mirror EvalTraceFormatter.content_from_message: string content only, and for
// tool messages unwrap the Kiln task-tool JSON to just its `output` field.
function flattener_content(message: TraceMessage): string | null {
  if (
    !("content" in message) ||
    typeof message.content !== "string" ||
    message.content.length === 0
  ) {
    return null
  }
  if (trace_role(message) === "tool") {
    try {
      const parsed = JSON.parse(message.content)
      if (parsed && typeof parsed === "object" && "output" in parsed) {
        // The server returns parsed["output"] verbatim; only a string output
        // reproduces its bytes here. A non-string output would need Python's
        // repr, which we can't match — leave it and let the byte-guard in the
        // mapper reject the block rather than highlight the wrong span.
        return typeof parsed.output === "string" ? parsed.output : null
      }
    } catch {
      // Not JSON — the formatter returns the content as-is.
    }
  }
  return message.content
}

function flattener_reasoning(message: TraceMessage): string | null {
  if (
    "reasoning_content" in message &&
    typeof message.reasoning_content === "string" &&
    message.reasoning_content.length > 0
  ) {
    return message.reasoning_content
  }
  return null
}

// Mirror EvalTraceFormatter.formatted_tool_calls_from_message: one
// "- Tool Name: …\n- Arguments: …" per call, concatenated with NO separator.
function flattener_tool_calls(message: TraceMessage): string | null {
  if (!("tool_calls" in message) || !message.tool_calls) return null
  const calls = message.tool_calls
  if (!Array.isArray(calls) || calls.length === 0) return null
  let out = ""
  for (const call of calls) {
    const fn = "function" in call ? call.function : undefined
    const name = fn && typeof fn.name === "string" ? fn.name : ""
    const args = fn && typeof fn.arguments === "string" ? fn.arguments : ""
    out += `- Tool Name: ${name}\n- Arguments: ${args}`
  }
  return out.length > 0 ? out : null
}

// The name of the tool call a tool message answers (matched by tool_call_id),
// searched across the whole trace — mirrors origin_tool_call_name_from_message.
// Its presence is what lets a tool message emit a block at all.
function has_origin_tool_call(
  message: TraceMessage,
  trace: TraceMessage[],
): boolean {
  const id =
    "tool_call_id" in message && typeof message.tool_call_id === "string"
      ? message.tool_call_id
      : null
  if (!id) return false
  for (const m of trace) {
    if (!("tool_calls" in m) || !Array.isArray(m.tool_calls)) continue
    for (const call of m.tool_calls) {
      if ("id" in call && call.id === id) return true
    }
  }
  return false
}

type EmittedBlock = {
  role_label: string
  tag: string
  content: string
  kind: TraceHighlightKind
}

// The single block one message flattens to (or null). Precedence mirrors the
// formatter: a tool message emits its result ONLY when its origin call is
// found; otherwise reasoning → tool_calls → content, where each present block
// OVERWRITES the prior (the lossy rule — content wins when a message carries
// both reasoning/tool calls and content).
function emitted_block(
  message: TraceMessage,
  trace: TraceMessage[],
): EmittedBlock | null {
  const role = trace_role(message)
  const content = flattener_content(message)

  if (role === "tool" && content) {
    if (!has_origin_tool_call(message, trace)) return null
    return {
      role_label: role,
      tag: `${role}_tool_message`,
      content,
      kind: "tool_result",
    }
  }

  let block: EmittedBlock | null = null
  const reasoning = flattener_reasoning(message)
  if (reasoning) {
    block = {
      role_label: `${role} reasoning`,
      tag: `${role}_reasoning_message`,
      content: reasoning,
      kind: "reasoning",
    }
  }
  const tool_calls = flattener_tool_calls(message)
  if (tool_calls) {
    block = {
      role_label: `${role} requested tool calls`,
      tag: `${role}_requested_tool_calls`,
      content: tool_calls,
      kind: "tool_calls",
    }
  }
  if (content) {
    block = {
      role_label: role,
      tag: `${role}_message`,
      content,
      kind: "content",
    }
  }
  return block
}

// Recompute the flattener's output string and record each block's absolute
// span. The "\n\n" separator is keyed on the RAW trace index (matching the
// formatter's `if index > 0`), not on emit order.
function flatten_output_blocks(trace: TraceMessage[]): FlattenedBlock[] {
  const blocks: FlattenedBlock[] = []
  let length = 0
  trace.forEach((message, index) => {
    const block = emitted_block(message, trace)
    if (!block) return
    if (index > 0) length += 2 // "\n\n"
    const header = `${block.role_label}:\n<${block.tag}>\n`
    const content_start = length + header.length
    const content_end = content_start + block.content.length
    blocks.push({
      trace_index: index,
      kind: block.kind,
      content_start,
      content_end,
      content: block.content,
    })
    // header + content + `\n</${tag}>`
    length = content_end + `\n</${block.tag}>`.length
  })
  return blocks
}

// Map a resolved [start, end) span in raw_output to the trace node it came
// from. Returns null when the span doesn't sit cleanly inside one block's text
// (e.g. it straddles the tag chrome or two messages), or when the recomputed
// layout doesn't match raw_output byte-for-byte at that offset — a mismatch
// means our port drifted from the server, so we surface NO highlight rather
// than a wrong one.
export function map_output_span_to_trace(
  trace: TraceMessage[],
  raw_output: string,
  span: { start: number; end: number },
): TraceHighlight | null {
  for (const block of flatten_output_blocks(trace)) {
    if (span.start >= block.content_start && span.end <= block.content_end) {
      if (
        raw_output.slice(block.content_start, block.content_end) !==
        block.content
      ) {
        return null
      }
      return {
        trace_index: block.trace_index,
        kind: block.kind,
        start: span.start - block.content_start,
        end: span.end - block.content_start,
      }
    }
  }
  return null
}

// ── Review-state helpers ─────────────────────────────────────────────────

export function build_trace_reviews(traces: TraceClaims[]): TraceReview[] {
  // Lazily-built traces start with no claim slots; the verdicts are sized
  // when their claims arrive (empty_claim_verdicts).
  return traces.map((t) => ({
    trace_id: t.trace_id,
    claim_verdicts: (t.claims ?? []).map(() => ({ agrees: null, why: "" })),
    final_judgement_verdict: { agrees: null, why: "" },
  }))
}

// Fresh positional verdict slots for a trace whose claims just arrived.
export function empty_claim_verdicts(claims: Claim[]): ClaimVerdict[] {
  return claims.map(() => ({ agrees: null, why: "" }))
}

// The blind final-judgement card for a trace whose claims build FAILED. The
// distilled claims never arrived, but the overall pass/fail call is still
// answerable from the transcript: judge_score pins the verdict headline and
// judge_reasoning is the only context (no citations — there are no built
// claim spans to anchor, so the reviewer opens the full trace to decide).
// Grading this lets an errored trace count as reviewed (is_trace_reviewed
// needs only the final judgement) and reach the save gate on the blind
// verdict alone — the sole recovery short of a paid re-drive.
export function blind_final_judgement(trace: TraceClaims): FinalJudgement {
  return {
    claim: trace.judge_reasoning,
    expected_result: trace.judge_score,
    evidence: "",
    citations: [],
  }
}

// A trace is reviewed once the final judgement has an agree/disagree and
// every disagreement (on any claim) carries a reason. Sub-claim verdicts are
// optional — we force only the overall call plus reasons for dissent.
export function is_trace_reviewed(
  trace: TraceClaims,
  review: TraceReview | undefined,
): boolean {
  if (!review) return false
  if (review.final_judgement_verdict.agrees === null) return false
  return [...review.claim_verdicts, review.final_judgement_verdict].every(
    (v) => v.agrees !== false || v.why.trim().length > 0,
  )
}

export function all_traces_reviewed(
  traces: TraceClaims[],
  reviews: TraceReview[],
): boolean {
  if (traces.length === 0 || reviews.length !== traces.length) return false
  return traces.every((t, i) => is_trace_reviewed(t, reviews[i]))
}

export function reviewed_trace_count(
  traces: TraceClaims[],
  reviews: TraceReview[],
): number {
  return traces.filter((t, i) => is_trace_reviewed(t, reviews[i])).length
}

// ── Subset review (multi-turn) ───────────────────────────────────────────

// How many traces the reviewer must rate: the human-rated golden answer key
// is capped at 25% of the chains server-side, so rating N//4 fills it
// exactly. Floor of 1 — a batch with no rated trace has no answer key.
export function review_target(total: number): number {
  if (total <= 0) return 0
  return Math.max(1, Math.floor(total / 4))
}

// The reviews the save gate demands during a calibration round: the standard
// target, capped by how many traces the round could actually surface. A
// re-judge shortfall can shrink the round's subset below floor(N/4), and
// demanding the full target then would deadlock the gate on traces the
// reviewer was never shown. First-round subsets are sized to the target, so
// this only ever bites mid-loop.
export function calibration_gate_target(
  total: number,
  subset_size: number,
): number {
  return Math.min(review_target(total), subset_size)
}

// Stratified pick of k indices from a candidate pool: ~50/50
// judge-pass/judge-fail so the answer key calibrates both classes (random or
// take-first selection degenerates on an imbalanced batch), topped up from
// the other bucket on shortfall, spread evenly across plan order within each
// bucket. Shared by the first-round subset and the calibration top-up.
function stratified_pick(
  traces: Pick<TraceClaims, "judge_score">[],
  candidates: number[],
  k: number,
): number[] {
  if (k >= candidates.length) return [...candidates].sort((a, b) => a - b)
  const fails: number[] = []
  const passes: number[] = []
  for (const i of candidates) {
    ;(traces[i]?.judge_score === "fail" ? fails : passes).push(i)
  }
  // Evenly-spaced picks across a bucket's plan order (k <= bucket.length
  // gives k distinct positions).
  const spread = (bucket: number[], n: number): number[] =>
    Array.from(
      { length: n },
      (_, j) => bucket[Math.floor((j * bucket.length) / n)],
    )
  // Fails get the odd slot: failure examples are usually the scarcer and
  // more informative half of an answer key.
  const want_fail = Math.min(fails.length, Math.ceil(k / 2))
  const want_pass = Math.min(passes.length, k - want_fail)
  const picked = new Set([
    ...spread(fails, want_fail),
    ...spread(passes, want_pass),
  ])
  // Shortfall top-up (one bucket smaller than its quota): fill from the
  // unpicked candidates, keeping the even spread across plan order.
  if (picked.size < k) {
    const unpicked = candidates.filter((i) => !picked.has(i))
    for (const i of spread(unpicked, k - picked.size)) picked.add(i)
  }
  return [...picked].sort((a, b) => a - b)
}

// Deterministic pick of which traces to put in front of the reviewer:
// judge-stratified over the whole batch. Purely mechanical — no LLM in the
// selection loop. This is the exact set the reviewer grades: unselected
// traces are not surfaced in review (they fill the train split unrated).
// Returns ascending indices into `traces`.
export function select_review_subset(
  traces: Pick<TraceClaims, "judge_score">[],
): number[] {
  return stratified_pick(
    traces,
    traces.map((_, i) => i),
    review_target(traces.length),
  )
}

// Which traces a calibration round asks the reviewer to re-grade, sized by
// the same review_target math as the first round. Priority order: traces the
// reviewer previously disagreed on (did the refine fix them?), then traces
// whose verdict flipped under the refined judge (its behavior changed there),
// then a fresh stratified top-up of never-reviewed traces (a held-out check
// against overfitting the judge to one sample). Verdicts are binary, so
// within each stratum stable plan order (ascending index) decides; on
// overflow disagreed take precedence over flips over fresh. Only traces
// holding a fresh verdict this round are eligible — a case that failed to
// re-judge kept a stale result, and nothing stale may be re-presented for
// grading. Returns ascending indices into `traces`.
export function select_calibration_subset(
  traces: Pick<TraceClaims, "judge_score">[],
  round: {
    // Indices the reviewer disagreed with last round.
    disagreed: number[]
    // Indices whose verdict flipped under the refined judge.
    flipped: number[]
    // Indices graded in any earlier round — excluded from the fresh top-up.
    reviewed: number[]
    // Indices that re-judged successfully this round (fresh verdicts).
    judged: number[]
  },
): number[] {
  const target = review_target(traces.length)
  const judged = new Set(round.judged)
  const reviewed = new Set(round.reviewed)
  const picked = new Set<number>()
  const take = (indices: number[]) => {
    for (const i of [...indices].sort((a, b) => a - b)) {
      if (picked.size >= target) return
      if (judged.has(i)) picked.add(i)
    }
  }
  take(round.disagreed)
  take(round.flipped)
  if (picked.size < target) {
    const fresh = round.judged.filter((i) => !picked.has(i) && !reviewed.has(i))
    for (const i of stratified_pick(traces, fresh, target - picked.size)) {
      picked.add(i)
    }
  }
  return [...picked].sort((a, b) => a - b)
}

// ── Save payload (per-claim grades) ──────────────────────────────────────

// The studio save contract IS in the generated schema — alias it (don't
// hand-mirror) so a backend change to the payload shape fails to compile here.
export type GradedClaim = components["schemas"]["GradedClaim"]
export type ClaimReviewPayload = components["schemas"]["ClaimReviewApi"]

function graded_claim(claim: Claim, verdict: ClaimVerdict): GradedClaim {
  return {
    claim: claim.claim,
    evidence: claim.evidence,
    expected_result: claim.expected_result,
    human_grade: verdict.agrees ? "agree" : "disagree",
    human_feedback: verdict.why.trim() || null,
  }
}

// Build the persisted per-claim grades for one reviewed trace. Only claims
// the reviewer actually graded are included (sub-claim verdicts are
// optional). Call only for a trace with BUILT claims: it throws otherwise,
// and a trace reviewed on the blind verdict alone (a failed claims build)
// carries no grades — the save path sends claim_review: null for those.
export function build_claim_review_payload(
  trace: TraceClaims,
  review: TraceReview,
): ClaimReviewPayload {
  if (!trace.final_judgement) {
    throw new Error("Cannot build a claim review before claims are built.")
  }
  return {
    judge_score: trace.judge_score,
    judge_reasoning: trace.judge_reasoning,
    claims: (trace.claims ?? [])
      .map((claim, i) => ({ claim, verdict: review.claim_verdicts[i] }))
      .filter(({ verdict }) => verdict && verdict.agrees !== null)
      .map(({ claim, verdict }) => graded_claim(claim, verdict)),
    final_judgement: graded_claim(
      trace.final_judgement,
      review.final_judgement_verdict,
    ),
  }
}

// The reviewer's overall verdict on a trace: the judge's verdict (the final
// judgement's expected_result is pinned to judge_score server-side), flipped
// when the human disagrees with the final judgement.
export function user_says_meets_spec(
  trace: TraceClaims,
  review: TraceReview,
): boolean {
  const judge_passes = trace.judge_score === "pass"
  return review.final_judgement_verdict.agrees === false
    ? !judge_passes
    : judge_passes
}

// Concatenated disagree-whys across all claims (incl. the final judgement) —
// the legacy free-text feedback field alongside the structured grades.
export function disagreement_feedback(review: TraceReview): string {
  return [...review.claim_verdicts, review.final_judgement_verdict]
    .filter((v) => v.agrees === false && v.why.trim())
    .map((v) => v.why.trim())
    .join(" ")
}

// ── Refine judge loop ─────────────────────────────────────────────────────

// One reviewed trace's grades shaped to feed judge refinement: the persisted
// ClaimReview payload plus a trace_label the refine model cites in rationales.
export type GradedTracePayload = ClaimReviewPayload & { trace_label: string }

// The refine model's proposed edit + its one-line rationale.
export type RefineJudgeChange = { change: string; rationale: string }

// The refine loop's response — a PROPOSAL, never auto-applied.
export type RefineJudgeProposal = {
  refined_judge_prompt: string
  changes: RefineJudgeChange[]
  not_incorporated_feedback: string | null
}

// Build the graded-traces payload for the refine call from the in-session
// review. Only reviewed traces with BUILT claims contribute (a half-reviewed
// trace is no signal, and refinement grades reference the claim text — a
// verdict-only review from a failed claims build has nothing to cite);
// trace_label is the durable run id when present, else the client trace id
// (opaque — the refine prompt tolerates that).
export function build_graded_traces(
  traces: TraceClaims[],
  reviews: TraceReview[],
): GradedTracePayload[] {
  return traces
    .map((trace, i) => ({ trace, review: reviews[i] }))
    .filter(
      ({ trace, review }) =>
        review &&
        is_trace_reviewed(trace, review) &&
        trace.claims_state === "built",
    )
    .map(({ trace, review }) => ({
      trace_label: trace.leaf_run_id || trace.trace_id,
      ...build_claim_review_payload(trace, review),
    }))
}

// How many graded traces carry a disagreement (on any claim or the final
// judgement). This is the loop's entry predicate as a count, so the review
// CTA flips to its refine label precisely when a save click would start a
// calibration round, and the tooltip can name the number honestly.
export function grade_disagreement_count(
  graded: Pick<ClaimReviewPayload, "claims" | "final_judgement">[],
): number {
  return graded.filter(
    (t) =>
      t.final_judgement.human_grade === "disagree" ||
      t.claims.some((c) => c.human_grade === "disagree"),
  ).length
}

// Whether the reviewer pushed back anywhere in the graded set — the signal
// that the judge needs refining before it ships.
export function has_grade_disagreement(
  graded: Pick<ClaimReviewPayload, "claims" | "final_judgement">[],
): boolean {
  return grade_disagreement_count(graded) > 0
}

// The refine CTA's tooltip: says what the click actually starts (a refine
// round, not a save) and what it costs the reviewer (one more review).
export function refine_judge_tooltip(num_disagreements: number): string {
  const conversations =
    num_disagreements === 1 ? "conversation" : "conversations"
  return `You disagreed with the judge on ${num_disagreements} ${conversations}. Kiln will improve the judge from your feedback and re-check your eval data, then you'll review once more.`
}

// Indices of traces carrying any explicit disagreement (on a claim or the
// final judgement) — the highest-priority stratum of the next round's subset.
export function disagreed_trace_indices(reviews: TraceReview[]): number[] {
  return reviews
    .map((review, i) => ({ review, i }))
    .filter(({ review }) =>
      [...review.claim_verdicts, review.final_judgement_verdict].some(
        (v) => v.agrees === false,
      ),
    )
    .map(({ i }) => i)
}

// ── Calibration loop (multi-turn) ────────────────────────────────────────
//
// After a review with disagreements, the judge is refined from the grades
// and re-scores every driven conversation; the reviewer then re-grades a
// freshly picked subset. The helpers below are the loop's pure core — round
// control, verdict flips, state rebuild — so the wizard component only wires
// streams and screens around them.

// One conversation's fresh verdict from a re-judge round. raw_input/
// raw_output/trace are the stream's echoes of the reloaded conversation —
// the same content as drive time, re-echoed so citations and the trace modal
// stay anchored to exactly what this round's judge saw.
export type RejudgeCaseResult = {
  judge_score: ExpectedResult
  judge_reasoning: string
  raw_input: string
  raw_output: string
  trace?: TraceMessage[] | null
}

// Indices whose pass/fail changed under the refined judge. Only re-judged
// cases can flip: a case with no fresh verdict is unknown, not unchanged.
export function flipped_indices(
  traces: Pick<TraceClaims, "judge_score">[],
  results: Map<number, Pick<RejudgeCaseResult, "judge_score">>,
): number[] {
  return [...results.entries()]
    .filter(([i, r]) => traces[i] && traces[i].judge_score !== r.judge_score)
    .map(([i]) => i)
    .sort((a, b) => a - b)
}

// Fold a re-judge round's verdicts into the trace list. Re-judged traces get
// the fresh verdict and their claims reset to unbuilt — claims argue a
// specific verdict, so they must be rebuilt against the new one. The new
// trace_id (unique per round) makes any still-in-flight claim build from the
// previous round miss the identity guard instead of corrupting the fresh
// state. Cases absent from `results` failed to re-judge and stay untouched.
export function apply_rejudge_results(
  traces: TraceClaims[],
  results: Map<number, RejudgeCaseResult>,
  round_tag: string,
): TraceClaims[] {
  return traces.map((t, i) => {
    const result = results.get(i)
    if (!result) return t
    return {
      ...t,
      trace_id: `${round_tag}_case_${i}`,
      judge_score: result.judge_score,
      judge_reasoning: result.judge_reasoning,
      raw_input: result.raw_input,
      raw_output: result.raw_output,
      trace: result.trace ?? t.trace,
      claims: null,
      final_judgement: null,
      claims_state: "unbuilt",
      claims_error: null,
    }
  })
}

// What a save request should do next. Multi-turn saves with disagreement
// enter a calibration round — as many rounds as it takes, since the loop
// only exits on convergence or the explicit save-without-refining link.
// Single-turn always saves — it has no saved conversations to re-judge, so
// no loop can run there.
export type SaveAction = { action: "save" } | { action: "calibrate" }

export function plan_save_action(args: {
  is_multi_turn: boolean
  has_disagreement: boolean
}): SaveAction {
  if (!args.is_multi_turn || !args.has_disagreement) return { action: "save" }
  return { action: "calibrate" }
}

// Which primary action the review CTA offers. Any disagreement enters a
// refine round; a review with zero disagreements saves — clearing the last
// disagreement flips the CTA back, which doubles as the convergence signal.
// The way out of the loop with disagreement remaining is the explicit
// save-without-refining link, not this CTA.
export type ReviewCta = "save" | "refine"

export function review_cta(args: { num_disagreements: number }): ReviewCta {
  return args.num_disagreements === 0 ? "save" : "refine"
}

// Whether save may quietly refine the judge from the grades. Multi-turn must
// not: its refinement runs explicitly in the calibration loop, and the judge
// that ships is exactly the one whose verdicts the reviewer graded.
// Single-turn keeps the quiet refine-with-fallback at save.
export function silent_refine_at_save(is_multi_turn: boolean): boolean {
  return !is_multi_turn
}

// The honest shortfall notice when some conversations couldn't be
// re-checked: they kept stale verdicts, so they were left out of the round.
export function rejudge_shortfall_notice(failed: number): string | null {
  if (failed <= 0) return null
  const conversations = failed === 1 ? "conversation" : "conversations"
  return `${failed} ${conversations} couldn't be re-checked with the improved judge and kept their previous results. They were left out of this review round.`
}

// A judge prompt/rubric this long is almost certainly runaway model output,
// not a rubric — reject it rather than persist it into the judge config.
export const MAX_JUDGE_PROMPT_CHARS = 20000

// Mechanically validate a refined judge prompt before it is written into the
// judge config. The prompt is inserted into the judge harness verbatim (then
// raw-wrapped server-side), so it must be plain text: non-empty, no Jinja /
// template braces, no code fences, and a sane length. Returns an error message
// to surface to the user, or null when the prompt is safe to apply. The
// refined prompt is a PROPOSAL from an LLM — never trust it into a write blind.
export function validate_refined_judge_prompt(prompt: string): string | null {
  const text = (prompt ?? "").trim()
  if (!text) return "The refined judge prompt is empty."
  if (text.length > MAX_JUDGE_PROMPT_CHARS) {
    return `The refined judge prompt is too long (${text.length} characters; max ${MAX_JUDGE_PROMPT_CHARS}).`
  }
  const forbidden: [RegExp, string][] = [
    [/\{\{|\}\}/, "Jinja expression braces ({{ or }})"],
    [/\{%|%\}/, "Jinja statement braces ({% or %})"],
    [/\{#|#\}/, "Jinja comment braces ({# or #})"],
    [/```/, "code fences"],
  ]
  for (const [pattern, label] of forbidden) {
    if (pattern.test(text)) {
      return `The refined judge prompt contains ${label}; it must be plain text.`
    }
  }
  return null
}

// ── The verdict card's reason line ────────────────────────────────────────

// The reason under the verdict card's deterministic headline. The claim
// builder's contract (kiln_server KIL-773) makes final_judgement.claim the
// substantive one-line reason ONLY — no verdict phrasing, "" when the model
// has nothing beyond the claims (including the server's synthesized
// backstop) — so this renders it verbatim and the empty string is the
// exact, non-heuristic signal for the card's evidence fallback. The old
// prefix-strip and circular-reason detection died with that contract.
export function final_judgement_reason(text: string): string {
  return text.trim()
}
