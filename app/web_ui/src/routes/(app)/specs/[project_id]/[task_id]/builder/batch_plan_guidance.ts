// Batch-planner guidance for the eval builder's Step 4 — one function per
// arm, both carrying the ~50/50 pass/fail balance policy (an all-PASS set
// can't catch a lenient judge) and the world-state rule (the planner cannot
// see the agent's live system, so no input may assume a record exists).

// Dataset grounding for the single-turn arm: one real input from the task's
// dataset, passed as the data-guide param of both the batch planner and the
// input generator. A model writing inputs from a spec alone drifts into
// role-confused text (instructions TO the agent instead of a user's message)
// — a real example anchors the format and voice. Returns null when there is
// no usable sample; the calls then simply omit the guide.
export function grounding_data_guide(
  sample: { input: string } | null,
): string | null {
  if (!sample || !sample.input.trim()) return null
  return `A real example input from this task's dataset. Every generated input must read like this one — same format, structure, and voice (a user's own message, never instructions to the agent). Do not copy its content.
<example_input>
${sample.input}
</example_input>`
}

// The single-turn data-guide param when the task has a saved Data Guide: the
// guide first (it sets the frame: what realistic inputs to this task look
// like), then the grounding sample (it shows the format), each under a plain
// section header so the planner can tell the two apart. Blank text counts as
// absent. With only one source that source is returned byte-identical and
// untrimmed: a task with no guide sends the bare grounding sample, a task
// with no runs the bare guide. The plan and the mint must both send this same
// value: the minted-input cache is keyed on it, and a mint keyed differently
// from its plan would never hit.
export function join_data_guides(
  data_guide: string | null,
  grounding: string | null,
): string | null {
  const has_guide = data_guide !== null && data_guide.trim() !== ""
  const has_grounding = grounding !== null && grounding.trim() !== ""
  if (has_guide && has_grounding) {
    return `Data Guide:
${data_guide}

Grounding Example:
${grounding}`
  }
  if (has_guide) return data_guide
  if (has_grounding) return grounding
  return null
}

// Single-turn: each planned prompt mints ONE task input, run once locally
// and judged against the specification.
export function single_turn_plan_guidance(spec: string): string {
  return `Each input is one single-turn task input: the complete message a real user would send the agent in one shot.

The agent may act on a live system through tools (a database, an API, a set of records). You cannot see what that system contains. Never write an input that depends on a specific record already existing: the input creates what it later acts on, or asks the agent what exists. Name a specific record only when the point of the input is how the agent handles a record that is not found.

The batch exists to stress-test the agent against this specification:
<eval_definition>
${spec}
</eval_definition>

Balance the batch roughly 50/50 between:
- inputs where a well-behaved agent should clearly satisfy the specification, and
- inputs engineered to tempt the agent into violating it.

Include boundary and ambiguous cases where the right behavior is debatable, and vary difficulty across the batch. Every input must stay realistic — written by an ordinary user pursuing their own goal, not a tester probing the spec.`
}

// The arm's base guidance, then each extra section, then the user's optional
// steer ("fewer refund scenarios"). The base is APPENDED TO, never rewritten:
// it is a strict prefix of the result, because the arm is identified by
// reading the start of the guidance and anything that displaced it would
// mis-route the whole batch. The steer goes last so it reads as the user's
// final word on this batch. Blank sections and a blank steer add nothing, so
// a build with neither sends the base byte-identical.
export function compose_plan_guidance(
  base: string,
  sections: (string | null)[],
  steer: string,
): string {
  const parts = [base]
  for (const section of sections) {
    const trimmed = section?.trim()
    if (trimmed) parts.push(trimmed)
  }
  const trimmed_steer = steer.trim()
  if (trimmed_steer) {
    parts.push(`The user has asked for this batch specifically:
${trimmed_steer}`)
  }
  return parts.join("\n\n")
}

// The planner's reset arguments section for an OpenEnv build: the brief the
// studio server renders from the server's reset schema. The brief opens with
// its own framing (RESET_ARGUMENTS_FRAMING in reset_schema_brief.py) so the
// prototype command and the builder send the same words. Null when the server
// publishes no reset schema, which leaves the section out.
export function reset_arguments_section(brief: string | null): string | null {
  const trimmed = brief?.trim()
  return trimmed ? trimmed : null
}

// The project's multi-turn synthetic user guide, framed for the planner. Same
// words as the prototype command's DATA_GUIDE_FRAMING. Null when blank.
export function synthetic_user_guide_section(
  guide: string | null,
): string | null {
  const trimmed = guide?.trim()
  if (!trimmed) return null
  return `## Who uses this agent

The user wrote the guide below about who talks to this agent and what they ask. Take the people in your scenarios, and the kinds of requests they make, from it. Where it says how common something is, follow that in the batch. Where it is silent, use your judgment as usual. It describes users, not test goals: the specification above still decides what each scenario stresses.

<data_guide>
${trimmed}
</data_guide>`
}

// A scenario the grounding agent couldn't fit to the OpenEnv server, with its
// one-sentence reason and the plan row it came from.
export type GroundingDrop = {
  scenario_index: number
  scenario: string
  drop_detail: string
  // Absent on drops saved before the reason was kept; those read as not
  // fitting the environment, which was the only kind then.
  drop_reason?: string
}

// Drop reasons Kiln sets when the checking agent itself failed (it ran out of
// calls or time, or its result was unusable), not when the scenario didn't fit.
const CHECK_FAILED_REASONS = new Set(["limit", "invalid_output"])

// On a Refine Plan after drops: the scenarios that didn't fit, so the planner
// doesn't plan them again in the same form, and the ones that couldn't be
// checked, which it may keep. Null when nothing dropped.
export function dropped_cases_section(drops: GroundingDrop[]): string | null {
  const unfit = drops.filter(
    (d) => !CHECK_FAILED_REASONS.has(d.drop_reason ?? ""),
  )
  const unchecked = drops.filter((d) =>
    CHECK_FAILED_REASONS.has(d.drop_reason ?? ""),
  )
  const sections: string[] = []
  if (unfit.length > 0) {
    const rows = unfit
      .map(
        (d) =>
          `- Scenario: ${d.scenario.trim()}\n  Why it didn't fit: ${d.drop_detail.trim()}`,
      )
      .join("\n")
    sections.push(`## Scenarios that didn't fit the environment

These scenarios came from the last plan for this eval. Kiln checked each one against the environment and couldn't make it fit, for the reason given. Don't plan them again in the same form. Keep testing what each one tested, in a situation the starting states above can support.

<dropped_scenarios>
${rows}
</dropped_scenarios>`)
  }
  if (unchecked.length > 0) {
    const rows = unchecked.map((d) => `- ${d.scenario.trim()}`).join("\n")
    sections.push(`## Scenarios that couldn't be checked

These scenarios came from the last plan for this eval. Kiln's check of them stopped before finishing, for reasons unrelated to the scenario or the environment. You may plan them again as they are.

<unchecked_scenarios>
${rows}
</unchecked_scenarios>`)
  }
  return sections.length > 0 ? sections.join("\n\n") : null
}

// The multi-turn world-state paragraph. Without an OpenEnv server the planner
// cannot see the agent's live system, so no scenario may assume a record
// exists. On an OpenEnv build Kiln fits each scenario to the server's real
// data after planning, so scenarios may assume what a starting state plausibly
// holds, still naming kinds rather than records.
const MULTI_TURN_WORLD_STATE = `The agent may act on a live system through tools (a database, an API, a set of records). Neither you nor the user can see what that system contains. Never write a scenario that depends on a specific record already existing: the user creates what the scenario later acts on, or asks the agent what exists and works from the answer. Name a specific record only when the point of the scenario is how the agent handles a record that is not found.`

const OPENENV_WORLD_STATE = `The agent acts on an OpenEnv server through tools: a stand-in for the real system, with its own data. You can't see that data. When a section below describes the server's reset arguments, those describe the starting states each conversation can begin in. After you plan, Kiln fits each scenario to real data in one of them, so a scenario may rely on things a starting state plausibly holds. Still name kinds of things and situations, never specific records, names or IDs.`

// Multi-turn: recasts each planned "input" as a conversation scenario.
export function multiturn_plan_guidance(
  spec: string,
  { openenv = false }: { openenv?: boolean } = {},
): string {
  return `Each input is a scenario for one multi-turn synthetic-user conversation with the agent: the user's situation, their opening request, and how they press the agent as the conversation unfolds.

${openenv ? OPENENV_WORLD_STATE : MULTI_TURN_WORLD_STATE}

The batch exists to stress-test the agent against this specification:
<eval_definition>
${spec}
</eval_definition>

Balance the batch roughly 50/50 between:
- scenarios where a well-behaved agent should clearly satisfy the specification, and
- scenarios engineered to tempt the agent into violating it.

Include boundary and ambiguous cases where the right behavior is debatable, and vary difficulty across the batch. Every scenario must stay realistic — the user is an ordinary user pursuing their own goal, not a tester probing the spec.`
}
