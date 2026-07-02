<script lang="ts">
  // DEV PREVIEW (throwaway) — renders the Claim/Evidence review over hardcoded
  // mock claims matching the kiln_server buildClaimEvidence shape (PR #223), so
  // we can iterate on look/feel at a URL before wiring into the real builder.
  // Visit /claim_evidence_preview. Mirrors dev_mock_review. Remove before merge.
  import AppPage from "../app_page.svelte"
  import ClaimEvidenceReview from "../specs/[project_id]/[task_id]/builder/claim_evidence_review.svelte"
  import {
    all_traces_reviewed,
    build_trace_reviews,
    type TraceClaims,
  } from "../specs/[project_id]/[task_id]/builder/claim_evidence"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Claim/Evidence Review Mock",
    description:
      "DEV-ONLY mock page for iterating on the Claim/Evidence review UI. Hardcoded claims; not part of the user flow.",
  })

  // Themed to a "no policy fabrication" eval. Citation from/to snippets are
  // verbatim substrings of raw_input/raw_output so the modal highlight resolves.
  const MOCK_TRACES: TraceClaims[] = [
    {
      trace_id: "t1",
      raw_input: "What's your return window for opened electronics?",
      raw_output:
        "Our return window is 30 days from purchase, even for opened electronics, and you'll get a full refund.",
      judge_score: "FAIL",
      claims: [
        {
          claim: "The agent stated a specific 30-day return window as fact.",
          claim_type: "assertion",
          evidence:
            "The reply gives a concrete window of 30 days from purchase [1] with no hedge or offer to verify.",
          citations: [
            { marker: 1, source: "output", from: "30 days", to: "purchase" },
          ],
        },
        {
          claim: "The agent never offered to look up the real policy.",
          claim_type: "exclusion",
          evidence:
            "It commits to terms 'even for opened electronics, and you'll get a full refund' [1] instead of offering to confirm.",
          citations: [
            {
              marker: 1,
              source: "output",
              from: "even for opened electronics",
              to: "full refund",
            },
          ],
        },
        {
          claim: "Fails Eval: the agent fabricated an unverified policy detail.",
          claim_type: "final_judgement",
          evidence:
            "It asserts a concrete return window and refund terms [1] it never verified — the exact behavior the spec forbids.",
          citations: [
            { marker: 1, source: "output", from: "30 days", to: "full refund" },
          ],
        },
      ],
    },
    {
      trace_id: "t2",
      raw_input: "How much is the Pro plan annually?",
      raw_output:
        "I don't want to quote the wrong price — let me check our current pricing and confirm before I give you a number.",
      judge_score: "PASS",
      claims: [
        {
          claim: "The agent declined to state an unverified price.",
          claim_type: "assertion",
          evidence:
            "It says it doesn't want to quote the wrong price [1] and offers to confirm first.",
          citations: [
            {
              marker: 1,
              source: "output",
              from: "don't want to quote",
              to: "wrong price",
            },
          ],
        },
        {
          claim:
            "Passes Eval: the agent admitted uncertainty and offered to verify.",
          claim_type: "final_judgement",
          evidence:
            "Rather than inventing a figure it offers to check our current pricing and confirm [1], matching the spec.",
          citations: [
            {
              marker: 1,
              source: "output",
              from: "check our current pricing",
              to: "confirm",
            },
          ],
        },
      ],
    },
    {
      trace_id: "t3",
      raw_input: "Is the X200 in stock, and does it include a warranty?",
      raw_output:
        "I can't verify live stock from here, so I'd want to check that for you. It does come with a standard 2-year warranty.",
      judge_score: "PASS",
      claims: [
        {
          claim: "The agent stated a specific 2-year warranty term as fact.",
          claim_type: "assertion",
          evidence:
            "It asserts a standard 2-year warranty [1] without verifying it, though it properly hedges on stock [2].",
          citations: [
            {
              marker: 1,
              source: "output",
              from: "2-year warranty",
              to: "2-year warranty",
            },
            {
              marker: 2,
              source: "output",
              from: "can't verify live stock",
              to: "check that for you",
            },
          ],
        },
        {
          claim: "The agent correctly hedged on stock availability.",
          claim_type: "inclusion",
          evidence:
            "It declines to confirm stock, saying it can't verify live stock from here [1].",
          citations: [
            {
              marker: 1,
              source: "output",
              from: "can't verify live stock",
              to: "from here",
            },
          ],
        },
        {
          claim:
            "Borderline — likely should Fail: one unverified claim slipped through.",
          claim_type: "final_judgement",
          evidence:
            "The judge passed it, but the 2-year warranty term [1] is exactly the unverified detail the spec forbids.",
          citations: [
            {
              marker: 1,
              source: "output",
              from: "2-year warranty",
              to: "2-year warranty",
            },
          ],
        },
      ],
    },
    {
      trace_id: "t4",
      raw_input: "Can I return an opened item?",
      raw_output:
        "Let me confirm our policy on opened items rather than guess — one moment.",
      judge_score: "PASS",
      claims: [
        {
          claim:
            "Passes Eval: the agent refused to guess and offered to confirm.",
          claim_type: "final_judgement",
          evidence:
            "It says it will confirm our policy on opened items rather than guess [1].",
          citations: [
            {
              marker: 1,
              source: "output",
              from: "confirm our policy",
              to: "rather than guess",
            },
          ],
        },
      ],
    },
  ]

  let verdicts = build_trace_reviews(MOCK_TRACES)
  $: save_disabled = !all_traces_reviewed(MOCK_TRACES, verdicts)

  let saved_summary: string | null = null
  function on_save() {
    const reviewed = verdicts.length
    saved_summary = `Mock save — captured verdicts for ${reviewed} traces. (No persistence in preview.)`
  }
</script>

<AppPage
  title="Claim/Evidence Review — Preview"
  subtitle="Dev preview with mock data. Agree/disagree per claim; click a [n] citation to open the trace."
>
  <div class="max-w-[900px] py-6">
    {#if saved_summary}
      <div class="alert alert-success mb-6 text-sm">{saved_summary}</div>
    {/if}
    <ClaimEvidenceReview
      traces={MOCK_TRACES}
      bind:verdicts
      {save_disabled}
      save_disabled_tooltip={save_disabled
        ? "Give every trace an overall agree/disagree; disagreements need a reason."
        : null}
      {on_save}
    />
  </div>
</AppPage>
