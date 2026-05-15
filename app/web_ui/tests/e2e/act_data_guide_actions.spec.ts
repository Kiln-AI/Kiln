import { test, expect } from "./fixtures"

const SEED_GUIDE =
  "# Reference Inputs\n\n## Example 1\n```input\nHello\n```\n\n# Input Guidelines & Rules\n\nBe concise and friendly."

async function seedDataGuide(
  apiRequest: import("@playwright/test").APIRequestContext,
  projectId: string,
  taskId: string,
  guide: string = SEED_GUIDE,
): Promise<void> {
  const resp = await apiRequest.put(
    `/api/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}/data_gen_guide`,
    { data: { guide } },
  )
  expect(
    resp.ok(),
    `PUT /data_gen_guide failed: ${resp.status()} ${await resp.text()}`,
  ).toBeTruthy()
}

/* @act
## Goals
On a fresh task, the /synth page intro is the single entry point for creating
an input data guide. Without a Kiln Pro key it shows one CTA: "Set Up Input
Data Guide" → /data_guide_setup. Clicking it lands on the manual setup form.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- /synth?reason=fine_tune triggers is_setup=true. With a fresh task and no
  saved guide, the "Create an Input Data Guide" Intro renders before the SDG
  wizard.
- Without a configured Kiln Pro key the primary CTA is "Set Up Input Data
  Guide" (manual). With one, it's "Set Up with Kiln Pro" + secondary "Set Up
  Manually".

## Assertions
- The "Set Up Input Data Guide" CTA navigates to /data_guide_setup.
*/
test("/synth intro routes to manual setup", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/generate/${project.id}/${task.id}/synth?reason=fine_tune`)

  await page.getByRole("button", { name: "Set Up Input Data Guide" }).click()

  await expect(page).toHaveURL(
    `/generate/${project.id}/${task.id}/data_guide_setup`,
  )
})

/* @act
## Goals
The Edit dialog on /data_guide offers two paths: "Verify Changes" (which
re-runs preview via the refine handoff) and "Save Without Verifying" (which
PUTs the edited examples directly, skipping the preview loop entirely). This
test covers the direct-PUT path: open Edit, modify the examples textarea,
click Save Without Verifying, confirm the new content is persisted.

## Fixtures
- registeredUser
- seededProjectWithTask
- apiRequest

## Hints
- Pre-seed a guide via PUT.
- The Edit action button is rendered by AppPage with label "Edit".
- The dialog's textarea has id="edit_guide_text".
- The "Save Without Verifying" affordance is a link styled <button> that
  appears below the FormContainer only when editing_guide !== guide
  (guide_refine_view.svelte).
- handle_save_without_verifying does not close the dialog itself; we verify
  via a fresh GET on /data_gen_guide rather than relying on dialog close.

## Assertions
- After clicking Save Without Verifying, GET /data_gen_guide returns
  guide equal to the user's edit (i.e. the PUT happened).
*/
test("edit dialog Save Without Verifying does a direct PUT", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await seedDataGuide(apiRequest, project.id, task.id)

  await page.goto(`/generate/${project.id}/${task.id}/data_guide`)

  await page.getByRole("button", { name: "Edit", exact: true }).click()

  const editedGuide = `# Reference Inputs\n\n## Example 1\n\`\`\`input\nedited-${Date.now()}\n\`\`\``
  await page.locator("#edit_guide_text").fill(editedGuide)

  await page.getByRole("button", { name: "Save Without Verifying" }).click()

  await expect
    .poll(
      async () => {
        const resp = await apiRequest.get(
          `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/data_gen_guide`,
        )
        if (!resp.ok()) return null
        const body = (await resp.json()) as { guide?: string }
        return body.guide ?? null
      },
      { timeout: 5000 },
    )
    .toBe(editedGuide)
})

/* @act
## Goals
On the saved-guide page, clicking the delete action button and confirming the
DeleteDialog must remove the saved guide and route the user to /synth. After
deletion, /data_guide must redirect back to setup (since the guide is gone).

## Fixtures
- registeredUser
- seededProjectWithTask
- apiRequest

## Hints
- Pre-seed a guide via PUT /api/projects/:pid/tasks/:tid/data_gen_guide.
- The delete action button on /data_guide is an icon-only button (no label),
  rendered by AppPage with <img src="/images/delete.svg">. Locate it by the
  image's src attribute.
- DeleteDialog renders inside Dialog.svelte; the destructive action_button
  has label "Delete" and uses the Dialog action_buttons rendering pattern.
- after_delete redirects to /generate/:pid/:tid/synth.

## Assertions
- After confirm, URL ends with /synth.
- Re-visiting /data_guide redirects to /data_guide_setup (guide is gone).
*/
test("delete data guide from saved-guide page", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await seedDataGuide(apiRequest, project.id, task.id)

  await page.goto(`/generate/${project.id}/${task.id}/data_guide`)

  await page.locator('button:has(img[src*="delete.svg"])').first().click()

  await page.getByRole("button", { name: "Delete", exact: true }).click()

  await expect(page).toHaveURL(`/generate/${project.id}/${task.id}/synth`)

  await page.goto(`/generate/${project.id}/${task.id}/data_guide`)
  await expect(page).toHaveURL(`/generate/${project.id}/${task.id}/synth`)
})
