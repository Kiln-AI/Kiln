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
an input data guide. The single primary CTA "Set Up Data Guide" routes to a
comparison page (`/data_guide_chooser`) that lets the user pick Manual vs
Kiln Pro. From there, "Create Manually" lands on the manual setup form.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- /synth?reason=fine_tune triggers is_setup=true. With a fresh task and no
  saved guide, the "Create a Data Guide" Intro renders before the SDG
  wizard.
- Intro CTAs: primary "Set Up Data Guide" → /data_guide_chooser, secondary
  "Continue Without" sets skip_data_guide=true (no nav).
- On the chooser, "Create Manually" no longer navigates directly: it opens
  the Add-Example dialog (include_output=false) first. The dialog captures
  one input, then handle_data_guide_example_added stashes it on the pending
  store and navigates to /data_guide_setup.
- The fixture task is plaintext with no runs, so the dialog skips method
  selection and renders the free-text input textarea (#example_input); the
  submit button is labelled "Add".

## Assertions
- "Set Up Data Guide" navigates to /data_guide_chooser.
- From the chooser, "Create Manually" → fill example → "Add" navigates to
  /data_guide_setup.
*/
test("/synth intro routes through chooser to manual setup", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/generate/${project.id}/${task.id}/synth?reason=fine_tune`)

  await page.getByRole("button", { name: "Set Up Data Guide" }).click()

  await expect(page).toHaveURL(
    `/generate/${project.id}/${task.id}/data_guide_chooser`,
  )

  await page.getByRole("button", { name: "Create Manually" }).click()

  // "Create Manually" opens the Add-Example dialog; fill the first input and
  // submit it to trigger the navigation to the manual setup form.
  await page.locator("#example_input").fill("First example input")
  await page.getByRole("button", { name: "Add", exact: true }).click()

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
- The Edit action button is rendered by AppPage with label "Edit". It opens
  an edit chooser dialog first (open_edit_chooser); pick "Edit Manually" to
  reach the textarea dialog (open_edit_dialog).
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

  // The Edit action opens a chooser first; pick manual editing to reach the
  // textarea dialog.
  await page.getByText("Edit Manually", { exact: true }).click()

  const editedGuide = `# Reference Inputs\n\n## Example 1\n\`\`\`input\nedited-${Date.now()}\n\`\`\``
  await page.locator("#edit_guide_text").fill(editedGuide)

  await page
    .getByRole("button", { name: "Save Without Verifying", exact: true })
    .click()

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
