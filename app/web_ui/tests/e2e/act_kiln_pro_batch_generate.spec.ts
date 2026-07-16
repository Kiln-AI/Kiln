import { test, expect } from "./fixtures"
import type { Page } from "@playwright/test"

/* @act
## Goals
Cover the second half of the Kiln Pro synthetic-data batch flow, downstream of the
Batch Plan screen (act_kiln_pro_batch_plan.spec.ts covers everything up to it):
generate inputs from the plan, generate outputs, remove a sample, and save the rest
into the dataset.

Inference is mocked. The batch plan comes from the mock kiln-server; input and output
generation go through the LOCAL studio_server batch endpoints, which call a real model
— so the mock openai_compatible provider stands in for it. Input generation uses
structured output, so its canned completions are JSON ({"generated_input": "..."});
output generation returns plaintext.

## Fixtures
- registeredUser
- seededProjectWithTask
- seededCopilotKey (skips the copilot connect screen)
- mockKilnServer (serves /v1/copilot/batch_plan; echoes one prompt per requested sample)
- connectedMockProvider (registers the mock as an openai_compatible provider)
- mockInferenceProvider (FIFO queue of canned completions)

## Hints
- Sample Count defaults to 50 — set it to 2, or the run would need 50 canned completions.
- The Generation Settings dialog's model defaults to ui_state.selected_model, so the
  test seeds the mock model there rather than driving the model dropdown.
- A dialog's submit button shares its accessible name with the page button that opens
  it, and a closed daisyUI modal is opacity-0 (which Playwright counts as visible) — so
  scope structurally: page buttons are the ones NOT inside a <dialog>, dialog buttons
  come from dialog[open].
- The row action menu opens on hover, not click.

## Assertions
- Inputs generate from the plan: both planned prompts land in the table with an input.
- Before outputs exist nothing is savable: Generate Outputs is offered, Save All is not.
- Outputs generate, and the batch becomes savable (Save All appears).
- Remove Sample drops the row from the table, and Save All's count follows it down.
- Saving reports what THIS save wrote ("Saved 1 new item."), not a running total.
*/

// gen_type=training via reason=fine_tune, and guide=skip so the data-guide step
// doesn't gate the chooser.
function synthUrl(projectId: string, taskId: string): string {
  return `/generate/${projectId}/${taskId}/synth?reason=fine_tune&guide=skip`
}

const SAMPLES = 2

// Each generation dialog's submit button carries the same accessible name as the
// page button that opens it ("Generate Batch (2)"), and a closed daisyUI modal is
// only opacity-0 — which Playwright still counts as visible — so neither a name
// nor a visibility filter separates them. Scope structurally instead:
//   - page_button: the one NOT inside a <dialog>.
//   - dialog: `[open]`, set only on the dialog actually showing.
function page_button(page: Page, name: string) {
  return page
    .getByRole("button", { name, exact: true })
    .locator("xpath=self::*[not(ancestor::dialog)]")
}

function dialog(page: Page) {
  return page.locator("dialog[open]")
}

test("kiln pro: generate inputs and outputs, remove a sample, save the rest", async ({
  page,
  registeredUser,
  seededProjectWithTask,
  seededCopilotKey,
  mockKilnServer,
  connectedMockProvider,
  mockInferenceProvider,
}) => {
  void registeredUser
  void seededCopilotKey
  void mockKilnServer
  const { project, task } = seededProjectWithTask

  // The run-config model defaults to ui_state.selected_model. Seeding it with the
  // mock model means the Generation Settings dialog opens ready to submit, so the
  // test doesn't have to drive the model dropdown to reach the flow it's covering.
  await page.addInitScript(
    ([pid, tid, model]) => {
      localStorage.setItem(
        "ui_state",
        JSON.stringify({
          current_project_id: pid,
          current_task_id: tid,
          selected_model: model,
        }),
      )
    },
    [
      project.id,
      task.id,
      `${connectedMockProvider.modelProviderName}/${connectedMockProvider.modelName}`,
    ] as const,
  )

  await page.goto(synthUrl(project.id, task.id))
  await expect(page.getByRole("button", { name: "Use Kiln Pro" })).toBeVisible({
    timeout: 15000,
  })
  await page.getByRole("button", { name: "Use Kiln Pro" }).click()

  // --- Generate Batch: plan two samples -------------------------------------
  await expect(
    page.getByRole("heading", { name: "Generate Synthetic Data Batch" }),
  ).toBeVisible({ timeout: 15000 })
  // Another "Count" stepper lives in a table on this page, so scope to the form.
  await page
    .locator("form")
    .filter({ hasText: "Sample Count" })
    .getByLabel("Count")
    .fill(String(SAMPLES))
  await page.locator("#batch_guidance").fill("Cover a range of edge cases.")
  await page.getByRole("button", { name: "Generate Batch" }).click()

  await expect(page.getByText("Batch Plan", { exact: true })).toBeVisible({
    timeout: 30000,
  })

  // --- Generate Inputs ------------------------------------------------------
  // Input generation is structured: one JSON completion per planned prompt.
  for (let i = 1; i <= SAMPLES; i++) {
    await mockInferenceProvider.queue({
      content: JSON.stringify({ generated_input: `mock input ${i}` }),
    })
  }

  await page_button(page, `Generate Batch (${SAMPLES})`).click()
  await expect(dialog(page)).toBeVisible()
  await dialog(page)
    .getByRole("button", { name: `Generate Batch (${SAMPLES})` })
    .click()

  // Every planned prompt becomes a row carrying its generated input. The collapsed
  // plan overview is a table too, so scope to the samples table by its Output column.
  const rows = page
    .locator("table")
    .filter({ has: page.getByRole("columnheader", { name: "Output" }) })
    .locator("tbody tr")
  await expect(rows).toHaveCount(SAMPLES, { timeout: 60000 })
  await expect(page.getByText("mock input 1")).toBeVisible({ timeout: 60000 })
  await expect(page.getByText("mock input 2")).toBeVisible()

  // Nothing is savable until outputs exist. (No "missing outputs" warning yet —
  // that only appears once an output run has been started and left gaps.)
  await expect(page_button(page, `Generate Outputs (${SAMPLES})`)).toBeVisible()
  await expect(page_button(page, `Save All (${SAMPLES})`)).toHaveCount(0)

  // --- Generate Outputs -----------------------------------------------------
  // Running the task on each input returns plaintext.
  for (let i = 1; i <= SAMPLES; i++) {
    await mockInferenceProvider.queue({ content: `mock output ${i}` })
  }

  await page_button(page, `Generate Outputs (${SAMPLES})`).click()
  await expect(dialog(page)).toBeVisible()
  await dialog(page)
    .getByRole("button", { name: "Generate Outputs", exact: true })
    .click()

  // With every output in hand, the batch becomes savable.
  await expect(page_button(page, `Save All (${SAMPLES})`)).toBeVisible({
    timeout: 60000,
  })

  // --- Remove a sample ------------------------------------------------------
  // The removed row leaves the table, and Save All counts down with it.
  // The row menu opens on hover; a click would open it on mouse-in and then
  // toggle it straight back shut.
  await rows.first().getByRole("button", { name: "More options" }).hover()
  await page.getByRole("button", { name: "Remove Sample" }).click()

  await expect(rows).toHaveCount(SAMPLES - 1)
  await expect(page_button(page, `Save All (${SAMPLES - 1})`)).toBeVisible()

  // --- Save -----------------------------------------------------------------
  await page_button(page, `Save All (${SAMPLES - 1})`).click()

  // The dialog reports what THIS save wrote, not a running total.
  await expect(page.getByText("Saved 1 new item.")).toBeVisible({
    timeout: 30000,
  })
  await expect(page.getByRole("link", { name: "dataset tab" })).toBeVisible()
})
