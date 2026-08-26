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

// Claims build lazily on both arms (the pipeline streams stop at the
// judge): "unbuilt" until the trace is selected/opened, then a
// build_claims round trip moves it through "building" to "built" or "error".
export type ClaimsBuildState = "unbuilt" | "building" | "built" | "error"

// One generated trace + the claims built for it. raw_input/raw_output are kept
// client-side so the trace modal can render them and resolve citation spans.
// leaf_run_id is the durable TaskRun identity on both arms — the chain leaf
// from run_cases_batch, or the single-turn pipeline's persisted run — that
// the save path writes the golden rating onto and calibration rounds
// re-judge through; null/"" when the runner emitted no id for a case.
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
  // The run's structured trace. On multi-turn it is what the judge saw and
  // raw_output is its lossy flattening; the trace modal renders THIS in the
  // house chat UI and remaps output-source citation spans back onto it. On
  // single-turn it is a UI-only echo (the judge scores the I/O pair).
  // Absent/null when the run recorded none — the modal keeps the raw view.
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
  const haystack = fold_typography(text)
  const from = fold_typography(citation.from)
  const to = fold_typography(citation.to)
  const start = haystack.indexOf(from)
  if (start < 0) return null
  const to_at = haystack.indexOf(to, start)
  if (to_at < 0) return null
  return { start, end: to_at + to.length }
}

// Curly punctuation folded to its straight form. Models retype anchors from
// text they read, so a citation often carries ' where the output has ’ and the
// anchor then misses. ONLY 1-code-unit-to-1-code-unit pairs belong here: the
// folded string must stay the same length as the original, since the spans
// resolved against it index the original text (they drive highlight slicing).
//
// Folding widens the match set rather than only rescuing misses: where the same
// snippet appears in the text in both quote styles, the first match can land on
// a different occurrence than before. Accepted — the variants are semantically
// the same sentence, so either occurrence is an honest highlight.
const TYPOGRAPHIC_FOLD: Record<string, string> = {
  "‘": "'",
  "’": "'",
  "“": '"',
  "”": '"',
}

// Derived from the map, never hand-written alongside it: a class listing a
// character the map lacks would substitute the string "undefined" and shift
// every offset after it, so the two cannot be allowed to drift.
const TYPOGRAPHIC_FOLD_PATTERN = new RegExp(
  `[${Object.keys(TYPOGRAPHIC_FOLD)
    .map((c) => c.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&"))
    .join("")}]`,
  "g",
)

function fold_typography(text: string): string {
  // `?? c` keeps an unmapped match length-preserving even if the two ever part.
  return text.replace(TYPOGRAPHIC_FOLD_PATTERN, (c) => TYPOGRAPHIC_FOLD[c] ?? c)
}

// ── Fold with an offset map (anchoring a citation in a RE-RENDERED string) ──
//
// The fold above is strictly 1:1, which is what lets a span resolved against it
// index the raw text. A field that PRETTY-PRINTS its content has no such
// luxury: `{"a":1}` reaches the reviewer as `{\n  "a": 1\n}`, so anchors the
// model retyped from the raw string miss the rendered one on whitespace alone,
// and the field is stuck showing the raw blob to keep its mark.
//
// This generalizes the 1:1 fold: it still normalizes for matching, but it also
// records where each folded character came from, so a span found in folded
// space translates back into offsets that slice the ORIGINAL — here the
// pretty-printed string the reviewer is actually looking at.
//
// The rules are a transform table over RUNS of the original: each run is
// copied, swapped for a replacement, or dropped. Whitespace and typography are
// the two we need today; a markdown-strip fold (drop the `**`, keep the word)
// is the same shape and would be another rule rather than a second mechanism.

export type FoldRule = {
  // Matches ONE run to transform. Two things are required of it. It must not be
  // able to match the EMPTY string: a zero-width match consumes nothing, so its
  // replacement would be spurious characters in the folded string with no run
  // behind them. And it must match its own matches ANCHORED — `^(?:pattern)$`
  // against a run the pattern produced — because that is how the folder tells
  // which rule fired. A pattern anchored internally (`^…` or `…$` of its own,
  // or a lookaround reaching outside the run) breaks that and its runs are
  // copied through untouched instead.
  pattern: string
  // What the run becomes in the folded string. "" drops it entirely.
  replace: (run: string) => string
}

// A folded string plus where every character of it came from. map and map_end
// are separate because a folded character can stand for a WIDER run than
// itself: a span ending on a collapsed space has to stop past the whole run
// that space swallowed, and one starting on it has to start at that run's first
// character. Both arrays are folded.length long.
export type FoldedText = {
  folded: string
  // map[i] = index in the ORIGINAL string where folded[i]'s run begins.
  map: number[]
  // map_end[i] = index in the ORIGINAL just past that run. map[i] + 1 for a
  // character copied or swapped 1:1.
  map_end: number[]
}

export function fold_with_offsets(text: string, rules: FoldRule[]): FoldedText {
  const pattern = new RegExp(
    rules.map((r) => `(?:${r.pattern})`).join("|"),
    "g",
  )
  // Which rule produced a run is decided by re-testing the run against each
  // rule, not by counting capture groups in the alternation: a rule that
  // brought its own groups would shift that count and silently dispatch the
  // wrong rule. Same left-to-right precedence the alternation itself uses.
  const whole_run = rules.map((r) => new RegExp(`^(?:${r.pattern})$`))
  let folded = ""
  const map: number[] = []
  const map_end: number[] = []
  let cursor = 0
  // Everything between two matched runs is carried over one character per
  // character, so its offsets are its own.
  const copy_verbatim = (until: number) => {
    for (let i = cursor; i < until; i++) {
      folded += text[i]
      map.push(i)
      map_end.push(i + 1)
    }
    cursor = until
  }
  for (const match of text.matchAll(pattern)) {
    const at = match.index ?? 0
    copy_verbatim(at)
    const run = match[0]
    // A zero-width match transformed nothing, so it produces nothing (see the
    // FoldRule contract). Emitting a replacement here would inject characters
    // the original never had and desync every offset after them.
    if (!run) continue
    const rule_index = whole_run.findIndex((re) => re.test(run))
    // No rule owns up to its own run: the pattern breaks the anchored-match
    // half of the contract. Copy the run through as ordinary text rather than
    // indexing past the end of the table — a fold that skips one run still
    // yields exact offsets, where a crash yields no citation at all.
    if (rule_index < 0) {
      copy_verbatim(at + run.length)
      continue
    }
    const rule = rules[rule_index]
    // By code UNIT, not code point: the maps are indexed the way the folded
    // string is, and a replacement carrying a surrogate pair would otherwise
    // add two characters against one entry and shift everything after it.
    const into = rule.replace(run)
    for (let k = 0; k < into.length; k++) {
      folded += into[k]
      map.push(at)
      map_end.push(at + run.length)
    }
    cursor = at + run.length
  }
  copy_verbatim(text.length)
  return { folded, map, map_end }
}

// Whitespace RUNS to a single space: `"a": 1,\n  "b"` and `"a": 1, "b"` fold
// the same, which covers the difference pretty-printing makes between two
// tokens that were already separated.
export const WHITESPACE_TOLERANT_FOLD: FoldRule[] = [
  { pattern: TYPOGRAPHIC_FOLD_PATTERN.source, replace: fold_typography },
  { pattern: "\\s+", replace: () => " " },
]

// Whitespace runs dropped outright. Pretty-printing also SEPARATES tokens that
// were flush — `{"a":1` becomes `{\n  "a": 1` — and no collapse can match a
// space against nothing, so this is the wider second pass. It is not the first
// because dropping whitespace lets a needle match across a word boundary; the
// collapsing fold gets to answer while it can.
export const WHITESPACE_FREE_FOLD: FoldRule[] = [
  { pattern: TYPOGRAPHIC_FOLD_PATTERN.source, replace: fold_typography },
  { pattern: "\\s+", replace: () => "" },
]

// resolve_citation_span's whitespace-tolerant twin, for anchoring a citation in
// a re-rendered copy of the text it was written against. Same anchor semantics
// (first `from`, then the first `to` at/after it), but the returned span slices
// the string PASSED IN rather than the raw one. Null when either anchor is
// absent, and when either carries no non-whitespace text to locate. Callers use
// it to place the mark in a pretty-printed body; a miss is a real miss and they
// fall back to the raw text.
export function resolve_citation_span_whitespace_tolerant(
  text: string,
  citation: Pick<Citation, "from" | "to">,
): { start: number; end: number } | null {
  return (
    resolve_span_in_fold(text, citation, WHITESPACE_TOLERANT_FOLD) ??
    resolve_span_in_fold(text, citation, WHITESPACE_FREE_FOLD)
  )
}

function resolve_span_in_fold(
  text: string,
  citation: Pick<Citation, "from" | "to">,
  rules: FoldRule[],
): { start: number; end: number } | null {
  const haystack = fold_with_offsets(text, rules)
  // The needle folds through the SAME rules, or the two would be normalized
  // into different alphabets and never meet.
  const from = fold_with_offsets(citation.from, rules).folded
  const to = fold_with_offsets(citation.to, rules).folded
  // An anchor with nothing but whitespace left in it — empty to begin with, or
  // emptied by the fold that drops whitespace — matches at every position and
  // covers none of them. That is not a resolution: reporting one hands the
  // caller a span it reads as success, and it loses the raw mark it would
  // otherwise have fallen back to.
  if (!/\S/.test(from) || !/\S/.test(to)) return null
  const start = haystack.folded.indexOf(from)
  if (start < 0) return null
  const to_at = haystack.folded.indexOf(to, start)
  if (to_at < 0) return null
  const end = to_at + to.length
  return {
    start: span_start(haystack, start),
    end: span_end(haystack, end - 1),
  }
}

// Where a resolved span starts and ends in the original. A folded whitespace
// character stands for a whole collapsed run, so a span that begins or ends on
// one steps over it: carrying it along would put the line break and indent
// pretty-printing inserted inside the <mark>, which on screen reads as a
// rendering bug rather than a citation. The two are symmetric — an anchor with
// a leading space is as ordinary as one with a trailing space.
function span_start(haystack: FoldedText, first: number): number {
  return /\s/.test(haystack.folded[first])
    ? haystack.map_end[first]
    : haystack.map[first]
}

function span_end(haystack: FoldedText, last: number): number {
  return /\s/.test(haystack.folded[last])
    ? haystack.map[last]
    : haystack.map_end[last]
}

// ── Structured-trace span mapping (MULTI-TURN ONLY) ──────────────────────
//
// The trace modal renders a MULTI-TURN conversation (TraceMessage[]) in the
// house chat UI, but citations resolve against raw_output — the server's
// FLATTENED rendering of that trace. This maps a resolved [start, end) span in
// raw_output back onto the trace: which message, which block kind, and the
// offset within that block's text, so the chat UI can highlight the exact node.
//
// Single-turn no longer reaches any of this: that arm renders two fields
// (single_turn_sections below) and marks a citation in the field's raw text
// directly, where the offsets already line up. The chat is the multi-turn
// renderer, so the mapping onto it is a multi-turn concern.
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
//
// Two raw_output shapes reach this: the flattened transcript above, and the
// unflattened case where raw_output is one message's content verbatim. The
// flattened walk runs first and the verbatim match is the fallback, so a
// trace that fits neither still yields no highlight.
export function map_output_span_to_trace(
  trace: TraceMessage[],
  raw_output: string,
  span: { start: number; end: number },
): TraceHighlight | null {
  return (
    map_span_in_flattened_layout(trace, raw_output, span) ??
    map_span_in_whole_message(trace, raw_output, span)
  )
}

function map_span_in_flattened_layout(
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

// Map a resolved [start, end) span in raw_input onto the conversation's
// opening user message. On multi-turn the input IS that message — the server
// derives raw_input from the first user message with non-empty string
// content, verbatim — so an input citation has an exact home in the chat:
// same string, same offsets. The pick mirrors the server's rule and the
// byte-identity guard rejects a raw_input that did not come from this
// trace's opening message (no highlight beats a wrong one).
export function map_input_span_to_trace(
  trace: TraceMessage[],
  raw_input: string,
  span: { start: number; end: number },
): TraceHighlight | null {
  const index = trace.findIndex(
    (message) =>
      trace_role(message) === "user" &&
      "content" in message &&
      typeof message.content === "string" &&
      message.content.length > 0,
  )
  if (index < 0) return null
  const message = trace[index]
  const content =
    "content" in message && typeof message.content === "string"
      ? message.content
      : ""
  if (content !== raw_input) return null
  if (span.start < 0 || span.end > raw_input.length) return null
  return {
    trace_index: index,
    kind: "content",
    start: span.start,
    end: span.end,
  }
}

// raw_output IS one message's content, with none of the flattener's role
// headers or tags, so the span's offsets carry onto that message
// unchanged. Requires exactly one byte-identical message — with two the
// cited one is ambiguous, and we'd rather show no highlight than the wrong one.
function map_span_in_whole_message(
  trace: TraceMessage[],
  raw_output: string,
  span: { start: number; end: number },
): TraceHighlight | null {
  const matches = trace
    .map((message, index) => ({ message, index }))
    .filter(
      ({ message }) => "content" in message && message.content === raw_output,
    )
  if (matches.length !== 1) return null
  if (span.start < 0 || span.end > raw_output.length) return null
  return {
    trace_index: matches[0].index,
    kind: "content",
    start: span.start,
    end: span.end,
  }
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

export function reviewed_trace_count(
  traces: TraceClaims[],
  reviews: TraceReview[],
): number {
  return traces.filter((t, i) => is_trace_reviewed(t, reviews[i])).length
}

// ── Trace-first review (gate + blind label) ──────────────────────────────

// Output length at or above which a review keeps the claim stack: past this
// the trace costs more to read than the claims that distill it.
// PLACEHOLDER pending calibration — captured single-turn outputs now span
// both sides of it, but the boundary has not been fit to reviewer data yet.
export const CHAR_CUTOFF = 900

// Which review shape a trace gets. Trace-first (read the trace, label the
// output) only where the raw trace is the cheaper read: one exchange, and
// short. Multi-turn transcripts and long outputs keep the claim stack.
// Length is the whole test because length is what predicts read cost. A
// structured output is not excluded: the Output section renders it through
// the house Output idiom, the same way Kiln shows output everywhere else, so
// it is legible on its own. It does occupy more lines per character than
// prose, since the cutoff counts the raw string while the section
// pretty-prints it, which is a consideration for whoever calibrates the
// cutoff. Excluding it outright would also put trace-first out of reach for
// most real single-turn tasks, which carry an output schema.
export function is_trace_first_review(args: {
  is_multi_turn: boolean
  raw_output: string
}): boolean {
  if (args.is_multi_turn) return false
  return args.raw_output.length < CHAR_CUTOFF
}

// What the inline trace renderer is fed: the run's own structured trace, or a
// two-message echo of the input/output pair when the run recorded none (the
// judge scored exactly that pair, so the echo is lossless). Throws when there
// is nothing to render rather than presenting an empty surface for a reviewer
// to label.
export function review_trace_messages(trace: TraceClaims): TraceMessage[] {
  if (trace.trace && trace.trace.length > 0) return trace.trace
  if (trace.raw_input || trace.raw_output) {
    return [
      { role: "user", content: trace.raw_input },
      { role: "assistant", content: trace.raw_output },
    ]
  }
  throw new Error("This trace has no transcript and no raw input or output.")
}

// ── Single-turn review sections ──────────────────────────────────────────
//
// A single-turn review is two sections, never chat bubbles: the Input the
// judge got, and the Output, which is everything in the trace after the first
// user turn. One exchange is not a conversation, and rendering it as one puts
// the input in a speech bubble and buries the answer the reviewer is grading.
//
// This resolves one trace into exactly what those sections render. Both
// single-turn surfaces (the inline trace-first review and the trace modal)
// read it, so the two cannot drift into different anatomies.

export type SingleTurnSections = {
  // The trace this was resolved from. The surfaces key their row mount on it,
  // so the rows remount (and re-apply their expansion) exactly when the
  // reviewer moves to a different trace.
  trace_id: string
  // The input as the judge got it, rendered as one field.
  input: string
  // The output's rows, when the messages carry more than an answer text — a
  // sequence to order (a tool loop), a message that recorded reasoning, or a
  // tool call standing in for an answer that never resolved. Null when one
  // message's content IS the whole output: an echoed pair, a stored record
  // pair and a traceless run all land here, and accordion chrome around a
  // single row is noise around the only thing being graded.
  rows: TraceMessage[] | null
  // Which of `rows` start expanded: the FINAL assistant message only. The rows
  // before it are the work, and their collapsed sequence is what shows its
  // shape at a glance; the final answer is what is being graded, so it costs
  // no click.
  expand_indices: number[]
  // The answer as text. Only resolved on the field path — with rows on screen
  // the messages speak for themselves, and "" there means unused, not empty.
  output: string
  // Why the Output section has nothing to show, when it has nothing. Scoped to
  // that section on purpose: an input the run really recorded must not be
  // hidden because its output is missing.
  output_error: string | null
}

// The messages the Output section covers: everything after the FIRST user
// turn, with system and developer turns dropped. The input has its own field,
// so repeating that turn as a row would show it twice, and the system prompt
// is task configuration rather than something the reviewer grades. A LATER
// user turn stays: on a surface that claims to show what happened after the
// input, dropping one would hide a turn the run really took.
function output_messages(messages: TraceMessage[]): TraceMessage[] {
  const first_user = messages.findIndex(
    (message) => trace_role(message) === "user",
  )
  const after = first_user < 0 ? messages : messages.slice(first_user + 1)
  return after.filter((message) => {
    const role = trace_role(message)
    return role !== "system" && role !== "developer"
  })
}

// A message's string content, or "" when it carries none.
function string_content(message: TraceMessage): string {
  return "content" in message && typeof message.content === "string"
    ? message.content
    : ""
}

// Whether a message recorded the model's thinking. A field renders answer text
// only, so a lone message carrying reasoning keeps the row that can hold both
// rather than having it dropped silently.
function records_reasoning(message: TraceMessage): boolean {
  return (
    "reasoning_content" in message &&
    typeof message.reasoning_content === "string" &&
    message.reasoning_content.trim().length > 0
  )
}

// Whether a message asked for tool calls — content a row renders and a field
// cannot, which is what makes it worth a row when no answer text resolved.
function requests_tool_calls(message: TraceMessage): boolean {
  return (
    "tool_calls" in message &&
    Array.isArray(message.tool_calls) &&
    message.tool_calls.length > 0
  )
}

// The answer the reviewer grades, for the single-message output a plain field
// renders: that message's content when it has any, else raw_output. The
// fallback is load-bearing rather than defensive — a function-calling run puts
// its answer in the tool call's arguments and stores content: null, so reading
// the message alone leaves the Output section EMPTY for a run that answered.
// Null when the trace holds neither; the caller decides what that means.
export function single_turn_output_text(
  trace: TraceClaims,
  row: TraceMessage | undefined,
): string | null {
  const content =
    row && trace_role(row) === "assistant" ? string_content(row) : ""
  if (content.trim()) return content
  return trace.raw_output.trim() ? trace.raw_output : null
}

// One trace resolved into the two sections. Throws only when the trace has no
// transcript and no raws (via review_trace_messages) — there is then no Input
// to show either. A missing OUTPUT is reported on the section instead, so the
// input still renders beside it.
export function single_turn_sections(trace: TraceClaims): SingleTurnSections {
  const rows = output_messages(review_trace_messages(trace))
  const sequence = rows.length > 1
  // Only the single-row case can reach a field, so that is the only case the
  // answer text is resolved for.
  const output = sequence ? null : single_turn_output_text(trace, rows[0])
  // Rows win on a sequence, on recorded reasoning, and as the last thing to
  // try before reporting nothing: a lone tool call is real content, so a run
  // whose answer never resolved still shows the call it made.
  const use_rows =
    sequence ||
    rows.some(records_reasoning) ||
    (output === null && rows.some(requests_tool_calls))
  let final_assistant = -1
  if (use_rows) {
    for (let i = rows.length - 1; i >= 0 && final_assistant < 0; i--) {
      if (trace_role(rows[i]) === "assistant") final_assistant = i
    }
  }
  return {
    trace_id: trace.trace_id,
    input: trace.raw_input,
    rows: use_rows ? rows : null,
    expand_indices: final_assistant >= 0 ? [final_assistant] : [],
    output: output ?? "",
    output_error:
      use_rows || output !== null ? null : "This trace recorded no output.",
  }
}

// The sections for one trace, or the reason there are none at all. Both
// single-turn surfaces read this rather than calling single_turn_sections
// directly, so a trace with nothing to render fails the same way on both.
export type SingleTurnSectionsResult = {
  sections: SingleTurnSections | null
  error: string | null
}

// A resolver that returns the SAME result object for the same trace content.
// The review page reassigns its whole trace array whenever a background claims
// build lands, which re-runs every reactive statement downstream; recomputing
// there would hand the row list a new array each time and remount it, closing
// whatever the reviewer had opened. Holds state, so each component instance
// makes its own.
export function single_turn_sections_resolver(): (
  trace: TraceClaims,
) => SingleTurnSectionsResult {
  // The inputs single_turn_sections actually reads. A claims build patches
  // other fields, and those must not count as a change.
  let key: Pick<
    TraceClaims,
    "trace_id" | "raw_input" | "raw_output" | "trace"
  > | null = null
  let result: SingleTurnSectionsResult = { sections: null, error: null }
  return (trace: TraceClaims) => {
    if (
      key &&
      key.trace_id === trace.trace_id &&
      key.raw_input === trace.raw_input &&
      key.raw_output === trace.raw_output &&
      key.trace === trace.trace
    ) {
      return result
    }
    key = {
      trace_id: trace.trace_id,
      raw_input: trace.raw_input,
      raw_output: trace.raw_output,
      trace: trace.trace,
    }
    try {
      result = { sections: single_turn_sections(trace), error: null }
    } catch (e) {
      result = {
        sections: null,
        error: e instanceof Error ? e.message : "This trace can't be shown.",
      }
    }
    return result
  }
}

// The blind label written as the verdict BOTH arms store: the reviewer says
// the output was right or wrong and agreement with the judge is computed from
// it (the user_says_meets_spec direction), so trace-first fills the same
// final_judgement_verdict slot the claim cards fill and the save, gate and
// refine paths need no arm of their own.
export function blind_label_agrees(
  judge_score: ExpectedResult,
  user_says_pass: boolean,
): boolean {
  return user_says_pass === (judge_score === "pass")
}

// That verdict read back as the reviewer's label. The verdict is what the
// review state keeps, so a revisited trace can show the label its reviewer
// already gave rather than a blank row. Null while the trace is ungraded.
export function blind_label_from_verdict(
  judge_score: ExpectedResult,
  agrees: boolean | null,
): boolean | null {
  if (agrees === null) return null
  return agrees === (judge_score === "pass")
}

// ── Subset review (both arms) ────────────────────────────────────────────

// How many traces the reviewer must rate: the human-rated golden answer key
// is capped at 25% of the batch runs server-side, so rating N//4 fills it
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

// The final judgement the reviewer actually graded. Dispatches on the same
// claims_state the review card renders from — "built" shows the distilled
// judgement, "error" the blind verdict card — so the payload grades exactly
// what was on screen. Null while the claims build is unbuilt or still
// running: nothing was presented to grade yet.
function reviewed_final_judgement(trace: TraceClaims): FinalJudgement | null {
  if (trace.claims_state === "built") return trace.final_judgement
  return trace.claims_state === "error" ? blind_final_judgement(trace) : null
}

// Build the persisted per-claim grades for one reviewed trace. Only claims
// the reviewer actually graded are included (sub-claim verdicts are
// optional). A trace reviewed on the blind verdict alone (a failed claims
// build) grades that verdict with claims: [] — an absent claim is no signal,
// never agreement. The save path deliberately diverges and persists
// claim_review: null for those: the in-session refine loop consumes the blind
// grade, but the persisted answer key records only reviews of built claims.
// Throws while the claims build is unbuilt or still running.
export function build_claim_review_payload(
  trace: TraceClaims,
  review: TraceReview,
): ClaimReviewPayload {
  const final_judgement = reviewed_final_judgement(trace)
  if (!final_judgement) {
    throw new Error("Cannot build a claim review before claims are built.")
  }
  // An ungraded overall call has no honest encoding: graded_claim would write
  // it as "disagree" while user_says_meets_spec reads it as agreement, so the
  // same record would contradict itself in the answer key. Callers gate on
  // is_trace_reviewed; this refuses rather than guesses if one ever doesn't.
  if (review.final_judgement_verdict.agrees === null) {
    throw new Error("Cannot build a claim review before the trace is graded.")
  }
  return {
    judge_score: trace.judge_score,
    judge_reasoning: trace.judge_reasoning,
    claims: (trace.claims ?? [])
      .map((claim, i) => ({ claim, verdict: review.claim_verdicts[i] }))
      .filter(({ verdict }) => verdict && verdict.agrees !== null)
      .map(({ claim, verdict }) => graded_claim(claim, verdict)),
    final_judgement: graded_claim(
      final_judgement,
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
// review. Every reviewed trace contributes: one with built claims sends its
// claim grades, one reviewed on the blind verdict alone sends that verdict
// with claims: []. Leaving the blind ones out dropped their disagreements
// from grade_disagreement_count, so a review that disputed only blind
// verdicts saw the plain Save CTA and shipped an un-refined judge the
// reviewer had contradicted (disagreed_trace_indices counted that same trace,
// and an all-blind refine retry had no traces to send). Half-reviewed traces
// are no signal and stay out; trace_label is the durable run id when present,
// else the client trace id (opaque — the refine prompt tolerates that).
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
        reviewed_final_judgement(trace) !== null,
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
// judged_noun is the arm's word for one reviewed item — the wizard reviews
// conversations in multi-turn and examples in single-turn.
export function refine_judge_tooltip(
  num_disagreements: number,
  judged_noun: string,
): string {
  const items = num_disagreements === 1 ? judged_noun : `${judged_noun}s`
  return `You disagreed with the judge on ${num_disagreements} ${items}. Kiln will improve the judge from your feedback and re-check your eval data, then you'll review once more.`
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

// ── Calibration loop ──────────────────────────────────────────────────────
//
// After a review with disagreements, the judge is refined from the grades and
// re-scores the eval data; the reviewer then re-grades against the refined
// judge's verdicts. Both arms run the same round: judge_traces re-judges the
// saved runs by durable id (verdicts only — claims rebuilt lazily for the
// next subset), select_calibration_subset picks what the reviewer re-grades,
// and cases that failed to re-judge keep stale verdicts and sit the round
// out. The helpers below are the loop's pure core — round control, verdict
// flips, state rebuild — so the wizard component only wires streams and
// screens around them.

// One case's fresh verdict from a re-judge round. raw_input/raw_output/
// trace are the stream's echoes of the reloaded run — the same content as
// drive time, re-echoed so citations and the trace modal stay anchored to
// exactly what this round's judge saw.
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

// What a save request should do next. A save with disagreement enters a
// calibration round on either arm — as many rounds as it takes, since the
// loop only exits on convergence or the explicit save-without-refining link.
// Arm-independent: unaddressed disagreement may never ship unseen.
export type SaveAction = { action: "save" } | { action: "calibrate" }

export function plan_save_action(args: {
  has_disagreement: boolean
}): SaveAction {
  return args.has_disagreement ? { action: "calibrate" } : { action: "save" }
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

// The honest shortfall notice when some cases couldn't be re-checked: they
// kept stale verdicts, so they were left out of the round. case_noun is the
// arm's word for one unit of eval data (conversation / test run).
export function rejudge_shortfall_notice(
  failed: number,
  case_noun: string,
): string | null {
  if (failed <= 0) return null
  const cases = failed === 1 ? case_noun : `${case_noun}s`
  return `${failed} ${cases} couldn't be re-checked with the improved judge and kept their previous results. They were left out of this review round.`
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
