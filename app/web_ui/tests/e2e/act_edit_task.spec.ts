import { test, expect } from "./fixtures"

/* @act
## Goals
Verify the edit task page loads an existing task and pre-populates the form from the
server. Navigating to /settings/edit_task/<project>/<task> for a seeded task must
fetch the task and show its name + instruction in the editable fields.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- Route is /settings/edit_task/{project_id}/{task_id}.
- Task Name field has id="task_name". Prompt/Instructions textarea has id="task_instructions".
- The page shows "Task ID: <id>" in the subtitle under the "Edit Task" heading.

## Assertions
- The Task Name input has the seeded task's name as its value.
- The Prompt / Task Instructions textarea has the seeded task's instruction as its value.
- The page subtitle contains the seeded task's id.
*/
test("edit task page loads existing task into form fields", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/settings/edit_task/${project.id}/${task.id}`)

  await expect(page.locator("#task_name")).toHaveValue(task.name)
  await expect(page.locator("#task_instructions")).toHaveValue(task.instruction)

  await expect(page.getByText(`Task ID: ${task.id}`)).toBeVisible()
})

/* @act
## Goals
Editing an existing task's name, prompt/instruction, and thinking instruction then
clicking "Save Task" must PATCH the backend so a subsequent GET returns the new values.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- Save button label is "Save Task" when editing (FormContainer submit_label).
- Editable fields: #task_name, #task_instructions, #thinking_instructions.

## Assertions
- After save, GET /api/projects/:pid/tasks/:tid returns the new name, instruction,
  and thinking_instruction.
*/
test("edit task page saves edits via PATCH", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/settings/edit_task/${project.id}/${task.id}`)
  await expect(page.locator("#task_name")).toHaveValue(task.name)

  const newName = `${task.name} (edited)`
  const newInstruction = `Edited prompt: ${task.instruction}`
  const newThinking = "Think step by step about the joke's setup first."

  await page.locator("#task_name").fill(newName)
  await page.locator("#task_instructions").fill(newInstruction)
  await page.locator("#thinking_instructions").fill(newThinking)

  await page.getByRole("button", { name: "Save Task" }).click()

  // The save PATCH races with our API check; assert via polling on the server.
  await expect
    .poll(async () => {
      const resp = await apiRequest.get(
        `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}`,
      )
      if (!resp.ok()) return null
      const body = await resp.json()
      return {
        name: body.name,
        instruction: body.instruction,
        thinking_instruction: body.thinking_instruction,
      }
    })
    .toEqual({
      name: newName,
      instruction: newInstruction,
      thinking_instruction: newThinking,
    })
})

/* @act
## Goals
When editing an existing task, the input and output JSON schemas are NOT editable.
Instead, the page shows read-only explanations and a "clone this task" link for each.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- The read-only copy mentions "You can't edit an existing task's input format" and
  the analogous output-format sentence.
- Each section links to /settings/clone_task/:pid/:tid with visible text "clone this task".

## Assertions
- Both the input and output "can't edit" messages are visible.
- At least one link with text "clone this task" points at /settings/clone_task/:pid/:tid.
*/
test("edit task page shows schemas as read-only with clone link", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/settings/edit_task/${project.id}/${task.id}`)
  await expect(page.locator("#task_name")).toHaveValue(task.name)

  await expect(
    page.getByText("You can't edit an existing task's input format"),
  ).toBeVisible()
  await expect(
    page.getByText("You can't edit an existing task's output format"),
  ).toBeVisible()

  const cloneLinks = page.getByRole("link", { name: "clone this task" })
  await expect(cloneLinks.first()).toHaveAttribute(
    "href",
    `/settings/clone_task/${project.id}/${task.id}`,
  )
})

/* @act
## Goals
Clicking the "Clone Task" action button in the page header navigates to the
/settings/clone_task/:pid/:tid route.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- The "Clone Task" button is an action button rendered by AppPage, located in the
  top-right corner of the Edit Task page.

## Assertions
- After clicking, the page URL matches /settings/clone_task/:pid/:tid.
*/
test("edit task page Clone Task button navigates to clone route", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/settings/edit_task/${project.id}/${task.id}`)
  await expect(page.locator("#task_name")).toHaveValue(task.name)

  await page.getByRole("button", { name: "Clone Task" }).click()

  await expect(page).toHaveURL(`/settings/clone_task/${project.id}/${task.id}`)
})

/* @act
## Goals
Clicking the delete icon in the Edit Task header opens a confirmation dialog;
clicking "Delete" in the dialog deletes the task via DELETE and redirects the
user to /setup/select_task.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- The delete action button is icon-only; its <img> src ends with /images/delete.svg.
- The confirmation dialog title is "Delete Task?".
- The dialog's confirm action button label is "Delete".

## Assertions
- The URL after confirmation is /setup/select_task.
- GET /api/projects/:pid/tasks/:tid returns 404 after the delete completes.
*/
test("edit task page delete button removes task and redirects", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/settings/edit_task/${project.id}/${task.id}`)
  await expect(page.locator("#task_name")).toHaveValue(task.name)

  await page.locator('button:has(img[src$="/images/delete.svg"])').click()

  const dialog = page.getByRole("dialog").filter({ hasText: "Delete Task?" })
  await expect(dialog).toBeVisible()
  await dialog.getByRole("button", { name: "Delete", exact: true }).click()

  await expect(page).toHaveURL("/setup/select_task")

  await expect
    .poll(async () => {
      const resp = await apiRequest.get(
        `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}`,
      )
      return resp.status()
    })
    .toBe(404)
})

/* @act
## Goals
The Edit Task page shows a "Settings" breadcrumb; clicking it navigates to /settings.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- The breadcrumb is rendered by AppPage as an <a href="/settings">Settings</a> link
  at the top of the page.

## Assertions
- Clicking the Settings breadcrumb changes the URL to /settings.
*/
test("edit task page Settings breadcrumb navigates to /settings", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/settings/edit_task/${project.id}/${task.id}`)
  await expect(page.locator("#task_name")).toHaveValue(task.name)

  await page
    .locator(".breadcrumbs")
    .getByRole("link", { name: "Settings" })
    .click()

  await expect(page).toHaveURL("/settings")
})
