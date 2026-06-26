<!--
  DEV-ONLY mock page for iterating on the multi-turn review paginator
  without running through the full eval-builder flow each time. Hardcodes
  10 plausible synthetic-user conversations and renders them through the
  same MultiTurnReviewPaginator the v2 builder uses.

  TODO(eval-v2): delete this route once the paginator UI is locked in.
  Reach via /dev_mock_review.
-->
<script lang="ts">
  import AppPage from "../app_page.svelte"
  import MultiTurnReviewPaginator, {
    type ReviewChain,
    type ChainVerdict,
  } from "../specs/[project_id]/[task_id]/builder/multi_turn_review_paginator.svelte"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Multi-Turn Review Mock",
    description:
      "DEV-ONLY mock page for iterating on the multi-turn review paginator UI. Hardcoded chains; not part of the user flow.",
  })

  // 10 plausible multi-turn conversations covering a range of lengths,
  // styles, and outcomes — picked to stress-test the paginator (short
  // turns vs long turns, polite vs frustrated personas, varying lengths).
  const chains: ReviewChain[] = [
    {
      case_index: 0,
      persona_summary:
        "First-time user, polite, exploring product features for a small team.",
      total_cost: 0.012,
      trace: [
        { role: "user", content: "Hi! Can you help me understand pricing?" },
        {
          role: "assistant",
          content:
            "Absolutely — we have three tiers: Free, Pro ($20/mo), and Team ($50/seat/mo). Pro unlocks Copilot, Team adds collaboration. What kind of usage are you planning?",
        },
        {
          role: "user",
          content: "Just a team of 3 people building prompts and evals.",
        },
        {
          role: "assistant",
          content:
            "Team is the right fit then — you get shared workspaces and SSO. Want me to walk through the eval features specifically?",
        },
      ],
    },
    {
      case_index: 1,
      persona_summary:
        "Frustrated power user — paid customer, hitting a known bug.",
      total_cost: 0.018,
      trace: [
        {
          role: "user",
          content:
            "I've been trying to export my dataset for 20 minutes and the button doesn't do anything. This is ridiculous.",
        },
        {
          role: "assistant",
          content:
            "I'm sorry about that. Can you tell me which browser you're using and roughly how large the dataset is (number of rows)?",
        },
        {
          role: "user",
          content: "Chrome, like 5000 rows.",
        },
        {
          role: "assistant",
          content:
            "5000 rows hits a known issue with the synchronous export. Workaround: use the CLI command `kiln dataset export --task-id X --format jsonl` — it handles larger sizes. I can paste the exact command if you share your task ID.",
        },
        {
          role: "user",
          content: "Task ID is abc123.",
        },
        {
          role: "assistant",
          content:
            "Run: `kiln dataset export --task-id abc123 --format jsonl --output ./dataset.jsonl` — should complete in under a minute.",
        },
      ],
    },
    {
      case_index: 2,
      persona_summary:
        "Technical user evaluating Kiln vs LangSmith for production eval.",
      total_cost: 0.022,
      trace: [
        {
          role: "user",
          content:
            "How does your eval framework handle multi-turn agent traces? LangSmith doesn't support those well.",
        },
        {
          role: "assistant",
          content:
            "Kiln's multi-turn synthetic-user runner drives realistic conversations against your agent, then a judge scores the full trace. You can re-run the same cases against different run configs to compare models. What's your scoring criteria — task success, tone, factual accuracy?",
        },
        {
          role: "user",
          content:
            "Task success primarily, but with tone as a secondary check.",
        },
        {
          role: "assistant",
          content:
            "Then you'd build two evals: one task-success spec (binary pass/fail), one tone spec (categorical). Both can run on the same multi-turn traces.",
        },
      ],
    },
    {
      case_index: 3,
      persona_summary: "Non-technical user, short blunt messages.",
      total_cost: 0.005,
      trace: [
        { role: "user", content: "where logs" },
        {
          role: "assistant",
          content:
            "Run logs live under the Runs tab on each task. Click any task in the sidebar to see them.",
        },
        { role: "user", content: "ok" },
      ],
    },
    {
      case_index: 4,
      persona_summary: "Curious developer, lots of follow-up questions.",
      total_cost: 0.031,
      trace: [
        {
          role: "user",
          content:
            "How does the judge get model selection? Can I use a local model?",
        },
        {
          role: "assistant",
          content:
            "By default the judge is GPT-4o via OpenRouter. You can override in eval config — local models via Ollama or LM Studio work too as long as they're registered in your Kiln settings.",
        },
        {
          role: "user",
          content:
            "Can the judge prompt be customized? I want to add specific red flags to look for.",
        },
        {
          role: "assistant",
          content:
            "Yes — the judge prompt is editable on the eval-config page. You can paste your own instructions, list red flags, and use Jinja2 templating for the trace placeholder.",
        },
        {
          role: "user",
          content: "Is Jinja2 templating documented somewhere?",
        },
        {
          role: "assistant",
          content:
            "Yes, at docs.kiln.tech/eval-templates — covers the available variables (trace, input, expected_output, etc.) and example templates.",
        },
      ],
    },
    {
      case_index: 5,
      persona_summary: "Skeptical buyer challenging product claims.",
      total_cost: 0.024,
      trace: [
        {
          role: "user",
          content:
            "You claim 'real eval scoring' but how is that different from a vibes check?",
        },
        {
          role: "assistant",
          content:
            "Fair question. The judge runs on a calibrated dataset — you mark a small sample golden, the judge's results are validated against your ratings before being trusted on the full eval set. If correlation is low, the eval-config page surfaces that.",
        },
        {
          role: "user",
          content: "So it's still a model judging another model.",
        },
        {
          role: "assistant",
          content:
            "Yes, and that's a known limitation. The mitigation is the calibration step — you can see exactly how well the judge agrees with you on golden examples before relying on its scores at scale.",
        },
      ],
    },
    {
      case_index: 6,
      persona_summary: "User testing edge cases — empty inputs, special chars.",
      total_cost: 0.009,
      trace: [
        { role: "user", content: "" },
        {
          role: "assistant",
          content:
            "Looks like your message came through empty. What were you trying to ask?",
        },
        {
          role: "user",
          content:
            "Sorry, I meant: can the eval handle inputs with special chars like {{ }} or backslashes?",
        },
        {
          role: "assistant",
          content:
            "Yes — inputs are escaped before being rendered into the judge prompt. Jinja2 statement delimiters in your data won't be interpreted as template syntax.",
        },
      ],
    },
    {
      case_index: 7,
      persona_summary:
        "Enterprise user asking about compliance and data residency.",
      total_cost: 0.027,
      trace: [
        {
          role: "user",
          content: "Where is task data stored? We need EU residency for GDPR.",
        },
        {
          role: "assistant",
          content:
            "All Kiln data is stored locally on your machine — there's no Kiln cloud for task data. The only outbound traffic is to LLM providers you've configured (and that traffic is governed by your provider agreements).",
        },
        {
          role: "user",
          content: "What about Copilot? That's a Kiln service.",
        },
        {
          role: "assistant",
          content:
            "Copilot runs on Kiln-managed infrastructure but doesn't persist your task data — only the request/response for the call you made. For full local-only operation, Pro features can be disabled and the manual workflow used instead.",
        },
      ],
    },
    {
      case_index: 8,
      persona_summary:
        "Long conversation, persona keeps refining requirements mid-conversation.",
      total_cost: 0.041,
      trace: [
        {
          role: "user",
          content: "I want to build an eval for customer support.",
        },
        {
          role: "assistant",
          content:
            "Good starting point. What does success look like for your support agent — resolving the issue, escalating appropriately, tone?",
        },
        { role: "user", content: "Resolving and tone." },
        {
          role: "assistant",
          content:
            "Two specs then. For 'resolves the issue' we'll need example conversations where the bot succeeded and failed. For 'tone' we'll need definitions of what acceptable tone looks like.",
        },
        {
          role: "user",
          content:
            "Actually — also escalation. We want it to escalate to a human after 3 failed attempts.",
        },
        {
          role: "assistant",
          content:
            "OK, third spec: 'escalates appropriately'. The trigger is 3 failed resolution attempts. We can encode that in the spec definition.",
        },
        {
          role: "user",
          content:
            "Wait, but what counts as a 'failed attempt'? The user saying 'that didn't work'?",
        },
        {
          role: "assistant",
          content:
            "Good question — that's exactly what we need to define in the spec. Let's draft: a 'failed attempt' is any turn where the user expresses dissatisfaction (e.g., 'that didn't work', 'still broken') or asks the same question again.",
        },
      ],
    },
    {
      case_index: 9,
      persona_summary: "Short, satisfied user — quick success.",
      total_cost: 0.006,
      trace: [
        { role: "user", content: "Thanks, this is exactly what I needed." },
        {
          role: "assistant",
          content: "Happy to help! Let me know if anything else comes up.",
        },
      ],
    },
  ]

  let verdicts: ChainVerdict[] = chains.map(() => ({
    verdict: null,
    feedback: "",
  }))

  // Mirror the builder's gating: every chain needs a verdict, every fail
  // needs feedback.
  $: all_reviewed =
    verdicts.length === chains.length &&
    verdicts.every(
      (v) =>
        v.verdict !== null &&
        (v.verdict !== "fail" || v.feedback.trim().length > 0),
    )
</script>

<!-- Mirror Step 5's real chrome from builder/+page.svelte so the mock
     renders exactly how it'll appear in the eval builder. -->
<div class="max-w-[1400px]">
  <AppPage
    title="Review Conversations"
    subtitle="Mark each conversation Pass or Fail."
    no_y_padding
  >
    <div class="py-6">
      <!-- Step indicator (matches builder's STEP_INDEX). -->
      <div class="text-sm text-gray-500 mb-6 flex items-center gap-2">
        <span>Step</span>
        <span class="font-medium">5</span>
        <span>of 6</span>
        <span class="badge badge-secondary badge-sm ml-2">multi-turn</span>
        <span
          class="badge badge-warning badge-sm ml-2"
          title="This route is for layout iteration only"
        >
          mock
        </span>
      </div>

      <MultiTurnReviewPaginator
        {chains}
        bind:verdicts
        on_back={() => alert("Back to Generate (mock)")}
        on_save={() => alert("Save → (mock)")}
        save_disabled={!all_reviewed}
        save_disabled_tooltip={all_reviewed
          ? null
          : "Mark each conversation pass or fail; failed conversations need a reason."}
      />
    </div>
  </AppPage>
</div>
