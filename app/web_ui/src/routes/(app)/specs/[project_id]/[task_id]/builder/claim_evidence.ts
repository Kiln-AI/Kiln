// Claim/Evidence review — client mirror of the kiln_server buildClaimEvidence
// task (PR #223). The contract is WIP on the server; keep this loosely coupled
// and re-sync if Mike tweaks the shape.
//
// The server task is PER-TRACE: one call distills one trace (raw_input +
// raw_output) plus the judge's decision into atomic claim/evidence pairs, so a
// reviewer can agree/disagree with each without reading the whole trace. The UI
// holds N of these (one per generated trace) and manages trace identity itself,
// since the server output carries no id.

// ── Server contract (mirror of BuildClaimEvidenceInput/Output) ───────────

export type ClaimType =
  | "inclusion" // an affirmative "X is included / present"
  | "exclusion" // a negative "X was left out, and why it qualified"
  | "assertion" // a single property of the output
  | "final_judgement" // the one overall pass/fail call (exactly one per trace)

export type CitationSource = "input" | "output"

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
  claim_type: ClaimType
  // One sentence with inline [n] markers; counter-points folded into a
  // "…, though …" clause. Markers resolve via `citations`.
  evidence: string
  citations: Citation[]
}

// What buildClaimEvidence returns for a single trace.
export type BuildClaimEvidenceOutput = { claims: Claim[] }

// What buildClaimEvidence takes for a single trace.
export type BuildClaimEvidenceInput = {
  raw_input: string
  raw_output: string
  eval_rubric: string
  judge_reasoning: string
  judge_score: string
}

// ── Client-side per-trace bundle ─────────────────────────────────────────

// One generated trace + the claims built for it. raw_input/raw_output are kept
// client-side so the trace modal can render them and resolve citation spans.
export type TraceClaims = {
  trace_id: string
  raw_input: string
  raw_output: string
  judge_score: string
  claims: Claim[]
}

// ── Human review (UI output) ─────────────────────────────────────────────

// Server claims carry no id, so verdicts are positional (index into
// TraceClaims.claims).
export type ClaimVerdict = {
  agrees: boolean | null // null = not yet reviewed
  why: string // required when the human disagrees — feeds the refine loop
}

export type TraceReview = {
  trace_id: string
  claim_verdicts: ClaimVerdict[]
}

// ── Display helpers ──────────────────────────────────────────────────────

// Claim types (inclusion/exclusion/assertion/final_judgement) are server-side
// signal, not shown to the reviewer — each claim is just a question to answer.
// Only the final_judgement type is used by the UI, to locate the overall call.

export function final_judgement_index(claims: Claim[]): number {
  return claims.findIndex((c) => c.claim_type === "final_judgement")
}

// ── Citation resolution ──────────────────────────────────────────────────

// Resolve a citation to a [start, end) span in its source text. Finds the
// first occurrence of `from`, then the first `to` at/after it (so `to` can sit
// later in the text; equal to `from` for a short span). Returns null if either
// anchor is absent — the UI then shows the citation without a highlight rather
// than highlighting the wrong place.
//
// Grep-safety note (Mike's open question): for repeated identical `from`
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

// ── Review-state helpers ─────────────────────────────────────────────────

export function build_trace_reviews(traces: TraceClaims[]): TraceReview[] {
  return traces.map((t) => ({
    trace_id: t.trace_id,
    claim_verdicts: t.claims.map(() => ({ agrees: null, why: "" })),
  }))
}

// A trace is reviewed once its final-judgement claim has an agree/disagree and
// every disagreement (on any claim) carries a reason. Sub-claim verdicts are
// optional — we force only the overall call plus reasons for dissent.
export function is_trace_reviewed(
  trace: TraceClaims,
  review: TraceReview | undefined,
): boolean {
  if (!review) return false
  const fj = final_judgement_index(trace.claims)
  if (fj >= 0 && review.claim_verdicts[fj]?.agrees === null) return false
  return review.claim_verdicts.every(
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
