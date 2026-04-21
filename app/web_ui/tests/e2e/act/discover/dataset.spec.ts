import { test, expect } from "../../fixtures"
import { BACKEND_URL } from "../../ports"

/* @act
## Goals
When the dataset has no runs, the page shows the empty state with a message
saying the dataset is empty and offers buttons to add data manually or
generate synthetic data.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- Route is /dataset/{project_id}/{task_id}.
- Empty state text includes "Your dataset for this task is empty."
- Two buttons: "Manually Add Data" and "Generate Synthetic Data".

## Assertions
- The empty state message is visible.
- "Manually Add Data" link is visible and points to the add_data route.
- "Generate Synthetic Data" link is visible and points to the generate route.
*/
test("dataset list page shows empty state when no data exists", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/dataset/${project.id}/${task.id}`)

  await expect(
    page.getByText("Your dataset for this task is empty."),
  ).toBeVisible()

  const addDataLink = page.getByRole("link", { name: "Manually Add Data" })
  await expect(addDataLink).toBeVisible()
  await expect(addDataLink).toHaveAttribute(
    "href",
    `/dataset/${project.id}/${task.id}/add_data`,
  )

  const synthLink = page.getByRole("link", { name: "Generate Synthetic Data" })
  await expect(synthLink).toBeVisible()
  await expect(synthLink).toHaveAttribute(
    "href",
    `/generate/${project.id}/${task.id}`,
  )
})

/* @act
## Goals
When the dataset has at least one run, the page shows a table with the expected
column headers and the run data is visible in the table.

## Fixtures
- registeredUser
- seededProjectWithTask
- apiRequest (to seed a run via POST)

## Hints
- Seed a run via POST /api/projects/:pid/tasks/:tid/runs with input, output, model_name, model_provider, tags.
- Table column headers: Rating, Repair State, Source, Model, Created At, Input Preview, Output Preview, Tags.
- The "Add Data" action button appears when data exists.

## Assertions
- The table is visible with correct column headers.
- The seeded run's input preview and output preview are visible in the table.
- The "Add Data" button is visible.
*/
test("dataset list page shows table with seeded run data", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  // Seed a run via the API
  const resp = await apiRequest.post(
    `${BACKEND_URL}/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/runs`,
    {
      data: {
        input: "Test input for dataset",
        output: "Test output for dataset",
        model_name: "test_model",
        model_provider: "test_provider",
        adapter_name: "test_adapter",
        tags: [],
      },
    },
  )
  expect(resp.ok(), "POST create run").toBeTruthy()

  await page.goto(`/dataset/${project.id}/${task.id}`)

  // Wait for table to appear
  const table = page.locator("table")
  await expect(table).toBeVisible()

  // Verify column headers
  for (const header of [
    "Rating",
    "Repair State",
    "Source",
    "Model",
    "Created At",
    "Input Preview",
    "Output Preview",
    "Tags",
  ]) {
    await expect(table.locator("th", { hasText: header })).toBeVisible()
  }

  // Verify seeded run data appears
  await expect(page.getByText("Test input for dataset")).toBeVisible()
  await expect(page.getByText("Test output for dataset")).toBeVisible()

  // Verify "Add Data" button appears
  await expect(page.getByRole("button", { name: "Add Data" })).toBeVisible()
})

/* @act
## Goals
Clicking the Select button enters select mode, showing checkboxes next to each row.
Clicking Cancel Selection exits select mode.

## Fixtures
- registeredUser
- seededProjectWithTask
- apiRequest (to seed a run)

## Hints
- The "Select" button toggles into select mode.
- In select mode, "Cancel Selection" button is visible.
- Checkboxes appear in each row when in select mode.

## Assertions
- Clicking "Select" makes checkboxes visible.
- Clicking "Cancel Selection" hides checkboxes and shows "Select" again.
*/
test("dataset list page select mode toggles checkboxes", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  // Seed a run
  const resp = await apiRequest.post(
    `${BACKEND_URL}/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/runs`,
    {
      data: {
        input: "Select mode test input",
        output: "Select mode test output",
        model_name: "test_model",
        model_provider: "test_provider",
        adapter_name: "test_adapter",
        tags: [],
      },
    },
  )
  expect(resp.ok()).toBeTruthy()

  await page.goto(`/dataset/${project.id}/${task.id}`)
  await expect(page.locator("table")).toBeVisible()

  // Enter select mode
  await page.getByRole("button", { name: "Select", exact: true }).click()

  // Checkboxes should now be visible
  await expect(page.locator("table tbody input[type=checkbox]")).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Cancel Selection" }),
  ).toBeVisible()

  // Exit select mode
  await page.getByRole("button", { name: "Cancel Selection" }).click()

  // "Select" button should be back
  await expect(
    page.getByRole("button", { name: "Select", exact: true }),
  ).toBeVisible()
  // Checkboxes should be gone
  await expect(
    page.locator("table tbody input[type=checkbox]"),
  ).not.toBeVisible()
})

/* @act
## Goals
In select mode, selecting a run and clicking the delete icon opens a confirmation
dialog. Confirming the delete removes the run from the backend.

## Fixtures
- registeredUser
- seededProjectWithTask
- apiRequest (to seed and verify run)

## Hints
- Enter select mode, click a row to select it, then click the delete icon button.
- The delete confirmation dialog title is "Delete Run" (for a single run).
- The dialog has a "Delete" button to confirm.

## Assertions
- After confirming delete, the run is removed (GET runs_summaries returns empty).
*/
test("dataset list page delete run via select mode", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  // Seed a run
  const createResp = await apiRequest.post(
    `${BACKEND_URL}/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/runs`,
    {
      data: {
        input: "Delete me",
        output: "Delete output",
        model_name: "test_model",
        model_provider: "test_provider",
        adapter_name: "test_adapter",
        tags: [],
      },
    },
  )
  expect(createResp.ok()).toBeTruthy()

  await page.goto(`/dataset/${project.id}/${task.id}`)
  await expect(page.locator("table")).toBeVisible()

  // Enter select mode
  await page.getByRole("button", { name: "Select", exact: true }).click()

  // Click the row to select it
  await page.locator("table tbody tr").first().click()

  // Click the delete icon button
  await page.locator('button:has(img[src$="/images/delete.svg"])').click()

  // Confirm deletion in dialog
  const dialog = page.getByRole("dialog").filter({ hasText: "Delete Run" })
  await expect(dialog).toBeVisible()
  await dialog.getByRole("button", { name: "Delete" }).click()

  // Verify the run is gone from the backend
  await expect
    .poll(async () => {
      const resp = await apiRequest.get(
        `${BACKEND_URL}/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/runs_summaries`,
      )
      if (!resp.ok()) return null
      const body = await resp.json()
      return (body as unknown[]).length
    })
    .toBe(0)
})

/* @act
## Goals
The add data page shows the correct title and data source options for the
default (generic) reason.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- Route is /dataset/{project_id}/{task_id}/add_data.
- Default title is "Add Samples to your Dataset".
- Options include "Synthetic Data" (recommended), "Add CSV", and "Manually Run Task".
- The Dataset breadcrumb is visible.

## Assertions
- Page title "Add Samples to your Dataset" is visible.
- "Synthetic Data", "Add CSV", and "Manually Run Task" options are visible.
- "Dataset" breadcrumb link is present.
*/
test("add data page shows data source options for generic reason", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/dataset/${project.id}/${task.id}/add_data`)

  await expect(page.getByText("Add Samples to your Dataset")).toBeVisible()

  await expect(page.getByText("Synthetic Data", { exact: true })).toBeVisible()
  await expect(page.getByText("Add CSV", { exact: true })).toBeVisible()
  await expect(
    page.getByText("Manually Run Task", { exact: true }),
  ).toBeVisible()

  // Verify Dataset breadcrumb
  const breadcrumb = page.locator(".breadcrumbs")
  await expect(breadcrumb.getByRole("link", { name: "Dataset" })).toBeVisible()
})

/* @act
## Goals
When the add data page is loaded with reason=eval, the title changes to
"Add Data for your Eval" and the breadcrumb links to the Specs & Evals page.

## Fixtures
- registeredUser
- seededProjectWithTask

## Hints
- Route is /dataset/{project_id}/{task_id}/add_data?reason=eval.
- Title: "Add Data for your Eval".
- Breadcrumb shows "Specs & Evals" linking to /specs/{project_id}/{task_id}.

## Assertions
- Page title "Add Data for your Eval" is visible.
- "Specs & Evals" breadcrumb is present.
*/
test("add data page shows eval-specific title and breadcrumb", async ({
  page,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  await page.goto(`/dataset/${project.id}/${task.id}/add_data?reason=eval`)

  await expect(page.getByText("Add Data for your Eval")).toBeVisible()

  const breadcrumb = page.locator(".breadcrumbs")
  await expect(
    breadcrumb.getByRole("link", { name: "Specs & Evals" }),
  ).toBeVisible()
})

/* @act
## Goals
The run detail page loads a seeded run and displays its input, output,
properties, and the "See All" toggle for advanced properties.

## Fixtures
- registeredUser
- seededProjectWithTask
- apiRequest (to seed a run)

## Hints
- Route is /dataset/{project_id}/{task_id}/{run_id}/run.
- Page title is "Dataset Run" with subtitle "Run ID: <id>".
- Input section has a heading "Input".
- Properties section has a heading "Properties".
- "See All" button toggles advanced properties.

## Assertions
- The page title "Dataset Run" is visible.
- The run ID is shown in the subtitle.
- The "Input" heading is visible.
- The "Properties" heading is visible.
- The "See All" button is visible and toggles to "See Less" on click.
*/
test("run detail page loads and shows run data with properties toggle", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  // Seed a run
  const resp = await apiRequest.post(
    `${BACKEND_URL}/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/runs`,
    {
      data: {
        input: "Run detail test input",
        output: "Run detail test output",
        model_name: "test_model",
        model_provider: "test_provider",
        adapter_name: "test_adapter",
        tags: [],
      },
    },
  )
  expect(resp.ok()).toBeTruthy()
  const run = await resp.json()

  await page.goto(`/dataset/${project.id}/${task.id}/${run.id}/run`)

  // Verify page title
  await expect(
    page.getByRole("heading", { name: "Dataset Run", exact: true }),
  ).toBeVisible()

  // Verify run ID is shown
  await expect(page.getByText(`Run ID: ${run.id}`)).toBeVisible()

  // Verify Input section
  await expect(page.getByText("Input").first()).toBeVisible()

  // Verify Properties section
  await expect(page.getByText("Properties", { exact: true })).toBeVisible()

  // Verify "See All" toggle
  const seeAllButton = page.getByRole("button", { name: "See All" })
  await expect(seeAllButton).toBeVisible()
  await seeAllButton.click()
  await expect(page.getByRole("button", { name: "See Less" })).toBeVisible()
})

/* @act
## Goals
On the run detail page, clicking the delete icon opens a confirmation dialog.
Confirming the deletion shows a "Run Deleted" badge.

## Fixtures
- registeredUser
- seededProjectWithTask
- apiRequest (to seed a run)

## Hints
- Delete button has img with src ending in /images/delete.svg.
- Confirmation dialog has title "Delete Dataset Run".
- After deletion, a "Run Deleted" badge is shown.

## Assertions
- After confirming delete, "Run Deleted" badge is visible.
- The run is deleted from the backend (GET returns 404).
*/
test("run detail page delete button removes run and shows deleted badge", async ({
  page,
  apiRequest,
  registeredUser,
  seededProjectWithTask,
}) => {
  void registeredUser
  const { project, task } = seededProjectWithTask

  // Seed a run
  const resp = await apiRequest.post(
    `${BACKEND_URL}/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/runs`,
    {
      data: {
        input: "Delete run detail test",
        output: "Delete run detail output",
        model_name: "test_model",
        model_provider: "test_provider",
        adapter_name: "test_adapter",
        tags: [],
      },
    },
  )
  expect(resp.ok()).toBeTruthy()
  const run = await resp.json()

  await page.goto(`/dataset/${project.id}/${task.id}/${run.id}/run`)
  await expect(page.getByText(`Run ID: ${run.id}`)).toBeVisible()

  // Click delete icon
  await page.locator('button:has(img[src$="/images/delete.svg"])').click()

  // Confirm in dialog
  const dialog = page
    .getByRole("dialog")
    .filter({ hasText: "Delete Dataset Run?" })
  await expect(dialog).toBeVisible()
  await dialog.getByRole("button", { name: "Delete" }).click()

  // Verify "Run Deleted" badge
  await expect(page.getByText("Run Deleted")).toBeVisible()

  // Verify backend deletion
  await expect
    .poll(async () => {
      const getResp = await apiRequest.get(
        `${BACKEND_URL}/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/runs/${encodeURIComponent(run.id)}`,
      )
      return getResp.status()
    })
    .toBe(404)
})
