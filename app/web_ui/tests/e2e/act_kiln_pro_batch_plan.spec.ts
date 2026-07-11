import { test, expect } from "./fixtures"

/* @act
## Goals
Drive the Kiln Pro synthetic-data batch flow end to end against the kiln-server
mock, and verify browser-back navigation between its stages.

The flow: synth chooser -> "Use Kiln Pro" -> Generate Batch page -> submit ->
Batch Plan screen. The batch plan request goes through the real client path
(studio_server -> kiln_server), so this also covers the batch_plan proxy.

Back-button behaviour is the point of the second test: each forward step pushes
a history entry, so the browser back button returns from the Batch Plan screen
to the Generate Batch page (rather than blowing past the whole flow).

## Fixtures
- registeredUser
- seededProjectWithTask
- seededCopilotKey (so the copilot connect screen is skipped)
- mockKilnServer (serves /v1/verify_api_key and /v1/copilot/batch_plan)

## Assertions
- The chooser renders and "Use Kiln Pro" reaches the Generate Batch page.
- Submitting reaches the Batch Plan screen with the mock's plan.
- Browser back from the Batch Plan screen returns to the Generate Batch page.
- "New Batch Plan" also returns to the Generate Batch page.
*/

// gen_type=training via reason=fine_tune, and guide=skip so the data-guide
// step doesn't gate the chooser.
function synthUrl(projectId: string, taskId: string): string {
  return `/generate/${projectId}/${taskId}/synth?reason=fine_tune&guide=skip`
}

async function gotoGenerateBatchPage(
  page: import("@playwright/test").Page,
  projectId: string,
  taskId: string,
) {
  await page.goto(synthUrl(projectId, taskId))

  // Chooser
  await expect(page.getByRole("button", { name: "Use Kiln Pro" })).toBeVisible({
    timeout: 15000,
  })
  await page.getByRole("button", { name: "Use Kiln Pro" }).click()

  // Generate Batch page (the merged intro + guidance form; no modal)
  await expect(
    page.getByRole("heading", { name: "Generate Batch" }),
  ).toBeVisible({ timeout: 15000 })
}

async function submitBatch(page: import("@playwright/test").Page) {
  // Guidance is a required field. For a fine-tuning task there's no spec to
  // prefill from, so it starts blank and must be filled before submitting.
  await page.locator("#batch_guidance").fill("Cover a range of edge cases.")
  // FormContainer appends a keyboard hint ("Generate Batch ⌘↵"), so don't match
  // exactly. The closed Generation Options dialog isn't in the a11y tree.
  await page.getByRole("button", { name: "Generate Batch" }).click()
}

test("kiln pro: chooser -> Generate Batch -> Batch Plan", async ({
  page,
  registeredUser,
  seededProjectWithTask,
  seededCopilotKey,
  mockKilnServer,
}) => {
  void registeredUser
  void seededCopilotKey
  void mockKilnServer
  const { project, task } = seededProjectWithTask

  await gotoGenerateBatchPage(page, project.id, task.id)

  // Submit the batch guidance form.
  await submitBatch(page)

  // Batch Plan screen, populated from the mock kiln server.
  await expect(page.getByText("Batch Plan", { exact: true })).toBeVisible({
    timeout: 30000,
  })
  await expect(
    page.getByText("Review the plan for generating your synthetic data batch."),
  ).toBeVisible()
})

test("kiln pro: browser back returns from Batch Plan to Generate Batch", async ({
  page,
  registeredUser,
  seededProjectWithTask,
  seededCopilotKey,
  mockKilnServer,
}) => {
  void registeredUser
  void seededCopilotKey
  void mockKilnServer
  const { project, task } = seededProjectWithTask

  await gotoGenerateBatchPage(page, project.id, task.id)
  await submitBatch(page)
  await expect(page.getByText("Batch Plan", { exact: true })).toBeVisible({
    timeout: 30000,
  })

  // The reported gap: browser back should land on the Generate Batch page,
  // not skip the whole Kiln Pro flow.
  await page.goBack()
  await expect(
    page.getByRole("heading", { name: "Generate Batch" }),
  ).toBeVisible()
  await expect(page.getByText("Batch Plan", { exact: true })).not.toBeVisible()
})

test("kiln pro: New Batch Plan returns to the Generate Batch page", async ({
  page,
  registeredUser,
  seededProjectWithTask,
  seededCopilotKey,
  mockKilnServer,
}) => {
  void registeredUser
  void seededCopilotKey
  void mockKilnServer
  const { project, task } = seededProjectWithTask

  await gotoGenerateBatchPage(page, project.id, task.id)
  await submitBatch(page)
  await expect(page.getByText("Batch Plan", { exact: true })).toBeVisible({
    timeout: 30000,
  })

  // Discarding the plan is destructive, so it confirms first.
  await page.getByRole("button", { name: "New Batch Plan" }).click()
  await expect(page.getByText("New Batch Plan?")).toBeVisible()
  await page.getByRole("button", { name: "New Plan (Discard Current)" }).click()

  await expect(
    page.getByRole("heading", { name: "Generate Batch" }),
  ).toBeVisible()
})
