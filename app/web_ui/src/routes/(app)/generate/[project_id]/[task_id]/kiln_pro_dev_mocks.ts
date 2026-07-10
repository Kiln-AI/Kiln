// TODO: remove before merging to main — dev-only scaffolding.
//
// Fake data for the Kiln Pro batch flow so the UI can be exercised without
// calling the copilot batch_plan API or burning LLM credits on generation.
// Flip KILN_PRO_DEV_MOCKS to true, reload, and the whole flow runs offline.
//
// Wired in at three call sites:
//   synth_kiln_pro.svelte  → submit_batch (batch plan)
//   kiln_pro_inputs.svelte → start_inputs / start_outputs

import type { components } from "$lib/api_schema"
import type { KilnError } from "$lib/utils/error_handlers"
import { writable, type Readable } from "svelte/store"
import type {
  BatchRun,
  InputsBatchStatus,
  OutputsBatchStatus,
} from "$lib/stores/kiln_pro_batch_store"

export const KILN_PRO_DEV_MOCKS = false

// How long a mocked plan takes, and how fast rows stream in.
const PLAN_DELAY_MS = 1500
const ROW_INTERVAL_MS = 400
// Every Nth row fails, so the error states stay on-screen during development.
const FAIL_EVERY = 7

type TaskRun = components["schemas"]["TaskRun-Output"]

const PROMPT_SEEDS = [
  "Enterprise customer disputing a duplicate $2,400 annual charge, polite but firm, references a ticket from three weeks ago",
  "First-time user unable to complete signup, mobile Safari, describes a blank screen after the email step",
  "Long-time subscriber requesting a downgrade, mentions budget cuts, asks about proration",
  "Angry customer, second follow-up, all caps in two sentences, threatens to churn",
  "Terse one-line request: password reset link expired",
  "Confused user who thinks they were charged twice but is looking at a pending authorization",
  "Detailed bug report with reproduction steps, browser version, and a pasted stack trace",
  "Non-native English speaker asking whether the annual plan includes support",
  "Customer asking for an invoice reissued to a new legal entity name after an acquisition",
  "Ambiguous message with no clear ask: 'this isn't working, please advise'",
]

function mock_prompt(i: number): string {
  const seed = PROMPT_SEEDS[i % PROMPT_SEEDS.length]
  // Past the seed list, suffix a counter so every prompt stays distinct.
  const cycle = Math.floor(i / PROMPT_SEEDS.length)
  return cycle === 0 ? seed : `${seed} (variant ${cycle + 1})`
}

function mock_summary(count: number): string {
  return [
    `Generating ${count} customer support messages spanning the **billing dispute** spec boundary.`,
    "",
    `- **Billing disputes**: 40% (${Math.round(count * 0.4)})`,
    `- **Account access**: 30% (${Math.round(count * 0.3)})`,
    `- **Plan changes**: 20% (${Math.round(count * 0.2)})`,
    `- **Ambiguous / no clear ask**: 10% (${Math.round(count * 0.1)})`,
    "",
    "Positive/negative split: 70% resolvable in one reply, 30% requiring escalation.",
  ].join("\n")
}

export function mock_batch_plan(
  count: number,
): Promise<{ prompts: string[]; summary: string }> {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        prompts: Array.from({ length: count }, (_, i) => mock_prompt(i)),
        summary: mock_summary(count),
      })
    }, PLAN_DELAY_MS)
  })
}

function mock_input(index: number): string {
  return `[mock input ${index + 1}] ${mock_prompt(index)}`
}

function mock_task_run(index: number, input: string): TaskRun {
  return {
    v: 1,
    id: `mock-run-${index + 1}`,
    input,
    output: {
      v: 1,
      output: `[mock output ${index + 1}] Acknowledged the customer's issue, confirmed the account, and proposed a resolution.`,
    },
  } as TaskRun
}

// Drives a mocked BatchRun: emits one more result every ROW_INTERVAL_MS until
// all rows land, then flips to "complete". Matches the real store's contract so
// the callers can swap one for the other.
function mock_batch_run<T>(
  total: number,
  build_status: (completed: number, errors: number, running: boolean) => T,
): BatchRun<T> {
  const status = writable<T | null>(null)
  const error = writable<KilnError | null>(null)
  let cancelled = false
  let completed = 0

  status.set(build_status(0, 0, total > 0))

  const timer = setInterval(() => {
    if (cancelled) return
    completed++
    const errors = Math.floor(completed / FAIL_EVERY)
    const running = completed < total
    status.set(build_status(completed, errors, running))
    if (!running) clearInterval(timer)
  }, ROW_INTERVAL_MS)

  if (total === 0) clearInterval(timer)

  return {
    status: status as Readable<T | null>,
    error,
    cancel: () => {
      cancelled = true
      clearInterval(timer)
    },
  }
}

function is_failed_row(index: number): boolean {
  return (index + 1) % FAIL_EVERY === 0
}

export function mock_inputs_batch(
  prompts: string[],
  model_name: string,
  model_provider: string,
): BatchRun<InputsBatchStatus> {
  return mock_batch_run<InputsBatchStatus>(
    prompts.length,
    (completed, errors, running) => ({
      status: running ? "running" : "complete",
      total: prompts.length,
      completed,
      errors,
      model_name,
      model_provider,
      results: Array.from({ length: completed }, (_, i) =>
        is_failed_row(i)
          ? { index: i, error: "Mock input generation failure." }
          : { index: i, input: mock_input(i) },
      ),
    }),
  )
}

export function mock_outputs_batch(
  items: { index: number; input: string | Record<string, unknown> }[],
): BatchRun<OutputsBatchStatus> {
  return mock_batch_run<OutputsBatchStatus>(
    items.length,
    (completed, errors, running) => ({
      status: running ? "running" : "complete",
      total: items.length,
      completed,
      errors,
      results: items.slice(0, completed).map((it, i) =>
        is_failed_row(i)
          ? { index: it.index, error: "Mock output generation failure." }
          : {
              index: it.index,
              task_run: mock_task_run(
                it.index,
                typeof it.input === "string"
                  ? it.input
                  : JSON.stringify(it.input),
              ),
            },
      ),
    }),
  )
}
