import { test, expect } from "../../fixtures"

test.describe("Optimize run configs", () => {
  /* @act
  ## Goals
  The optimize overview page loads and displays the page title "Optimize" with
  subtitle "Find the best way to run your task." and shows the "Optimization
  Strategies" heading with feature carousel cards.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /optimize/{project_id}/{task_id}
  - Page title is "Optimize"
  - Shows "Optimization Strategies" heading
  - FeatureCarousel displays cards like "Refine Prompt", "Compare Models", etc.

  ## Assertions
  - Page heading "Optimize" is visible.
  - "Optimization Strategies" heading is visible.
  - "Refine Prompt" text is visible in the carousel.
  - "Compare Models" text is visible in the carousel.
  - "Fine-Tune" text is visible in the carousel.
  */
  test("optimize overview shows title and optimization strategies", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/optimize/${project.id}/${task.id}`)

    await expect(
      page.getByRole("heading", { name: "Optimize", exact: true }),
    ).toBeVisible()

    await expect(
      page.getByRole("heading", { name: "Optimization Strategies" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Refine Prompt" }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Compare Models" }),
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "Fine-Tune" })).toBeVisible()
  })

  /* @act
  ## Goals
  The optimize overview page shows an empty state message when no run
  configurations exist, with text indicating the user should create one.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /optimize/{project_id}/{task_id}
  - "Run Configurations" heading is visible
  - Empty state shows "No run configurations yet" message
  - "Create Run Config" button is visible

  ## Assertions
  - "Run Configurations" heading is visible.
  - "No run configurations yet" text is visible.
  - "Create Run Config" button is visible.
  */
  test("optimize overview shows empty run configs state", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/optimize/${project.id}/${task.id}`)

    await expect(
      page.getByRole("heading", { name: "Run Configurations" }),
    ).toBeVisible()

    await expect(page.getByText("No run configurations yet")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Create Run Config" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Clicking the "Create Run Config" button on the optimize overview page opens
  a dialog titled "Create New Run Configuration".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /optimize/{project_id}/{task_id}
  - Button text is "Create Run Config"
  - Dialog title is "Create New Run Configuration"

  ## Assertions
  - After clicking "Create Run Config", dialog with heading "Create New Run Configuration" is visible.
  */
  test("optimize overview create run config button opens dialog", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/optimize/${project.id}/${task.id}`)

    await page.getByRole("button", { name: "Create Run Config" }).click()

    await expect(
      page.getByRole("heading", { name: "Create New Run Configuration" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Clicking the "Compare" button on the optimize overview page enables selection
  mode, showing "Cancel Selection" button and "0 selected" text.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /optimize/{project_id}/{task_id}
  - "Compare" button toggles selection mode
  - In selection mode: "Cancel Selection" button appears, "0 selected" text shows
  - The "Create Run Config" button is hidden during selection mode

  ## Assertions
  - After clicking "Compare", "Cancel Selection" button is visible.
  - "0 selected" text is visible.
  - "Create Run Config" button is not visible during selection mode.
  */
  test("optimize overview compare button enables selection mode", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/optimize/${project.id}/${task.id}`)

    await page.getByRole("button", { name: "Compare", exact: true }).click()

    await expect(
      page.getByRole("button", { name: "Cancel Selection" }),
    ).toBeVisible()

    await expect(page.getByText("0 selected")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Create Run Config" }),
    ).not.toBeVisible()
  })

  /* @act
  ## Goals
  Clicking "Cancel Selection" exits selection mode and restores the normal
  button state with "Compare" and "Create Run Config" buttons.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /optimize/{project_id}/{task_id}
  - Enter selection mode by clicking "Compare", then click "Cancel Selection"
  - After canceling, "Compare" and "Create Run Config" buttons return

  ## Assertions
  - After clicking "Cancel Selection", "Compare" button is visible again.
  - "Create Run Config" button is visible again.
  - "Cancel Selection" button is not visible.
  */
  test("optimize overview cancel selection exits selection mode", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/optimize/${project.id}/${task.id}`)

    await page.getByRole("button", { name: "Compare", exact: true }).click()

    await expect(
      page.getByRole("button", { name: "Cancel Selection" }),
    ).toBeVisible()

    await page.getByRole("button", { name: "Cancel Selection" }).click()

    await expect(
      page.getByRole("button", { name: "Compare", exact: true }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Create Run Config" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Cancel Selection" }),
    ).not.toBeVisible()
  })

  /* @act
  ## Goals
  The optimize overview page has a "Read the Docs" link pointing to the
  optimization documentation.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /optimize/{project_id}/{task_id}
  - "Read the Docs" is a sub-subtitle link
  - href is "https://docs.kiln.tech/docs/optimizers"

  ## Assertions
  - "Read the Docs" link is visible.
  - "Read the Docs" link has href "https://docs.kiln.tech/docs/optimizers".
  */
  test("optimize overview docs link has correct href", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/optimize/${project.id}/${task.id}`)

    await expect(
      page.getByRole("heading", { name: "Optimize", exact: true }),
    ).toBeVisible()

    const readDocsLink = page.getByRole("link", { name: "Read the Docs" })
    await expect(readDocsLink).toBeVisible()
    await expect(readDocsLink).toHaveAttribute(
      "href",
      "https://docs.kiln.tech/docs/optimizers",
    )
  })

  /* @act
  ## Goals
  The create run configuration page loads with the title "Create Run
  Configuration" and subtitle, and shows a form with a "Create" submit button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /optimize/{project_id}/{task_id}/run_config/create
  - Page title is "Create Run Configuration"
  - Subtitle is "Create a configuration to run your task."
  - Form has a "Create" submit button
  - Contains RunConfigComponent with model selector and prompt method

  ## Assertions
  - Page heading "Create Run Configuration" is visible.
  - "Create" button is visible.
  */
  test("create run config page shows form with create button", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/optimize/${project.id}/${task.id}/run_config/create`)

    await expect(
      page.getByRole("heading", { name: "Create Run Configuration" }),
    ).toBeVisible()

    await expect(page.getByRole("button", { name: "Create" })).toBeVisible()

    // Navigate away to prevent teardown race with page form handlers
    await page.goto("about:blank")
  })

  /* @act
  ## Goals
  The run config detail page loads for a specific run config and shows the
  "Run Configuration" title, breadcrumb back to Optimize, and action buttons
  for "Clone" and "Edit".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - First create a run config via API, then navigate to its detail page
  - Route is /optimize/{project_id}/{task_id}/run_config/{run_config_id}
  - Page title is "Run Configuration"
  - Breadcrumb shows "Optimize" link
  - Action buttons: "Clone" and "Edit"

  ## Assertions
  - Page heading "Run Configuration" is visible.
  - "Optimize" breadcrumb link is visible.
  - "Clone" button is visible.
  - "Edit" button is visible.
  */
  test("run config detail page shows properties and action buttons", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    // Create a run config via API
    const resp = await apiRequest.post(
      `/api/projects/${project.id}/tasks/${task.id}/run_configs`,
      {
        data: {
          name: "Test Run Config",
          run_config_properties: {
            type: "kiln_agent",
            model_name: "gpt_4o",
            model_provider_name: "openai",
            prompt_id: "simple_prompt_builder",
            structured_output_mode: "default",
          },
        },
      },
    )
    expect(resp.ok(), "POST run_configs").toBeTruthy()
    const runConfig = (await resp.json()) as { id: string }

    await page.goto(
      `/optimize/${project.id}/${task.id}/run_config/${runConfig.id}`,
    )

    await expect(
      page.getByRole("heading", { name: "Run Configuration", exact: true }),
    ).toBeVisible()

    await expect(page.getByRole("button", { name: "Clone" })).toBeVisible({
      timeout: 10000,
    })

    await expect(
      page.getByRole("button", { name: "Edit", exact: true }),
    ).toBeVisible()

    const breadcrumbs = page.locator(".breadcrumbs")
    await expect(
      breadcrumbs.getByRole("link", { name: "Optimize" }),
    ).toBeVisible()

    // Navigate away to prevent teardown race with page dialogs
    await page.goto("about:blank")
  })

  /* @act
  ## Goals
  The run config detail page shows an Edit dialog when the "Edit" button is
  clicked, with a field for "Run Configuration Name".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - First create a run config via API, then navigate to its detail page
  - Click "Edit" button to open EditDialog
  - Dialog has field labeled "Run Configuration Name"
  - Dialog title includes "Run Configuration"

  ## Assertions
  - After clicking "Edit", dialog with "Run Configuration Name" field is visible.
  */
  test("run config detail edit button opens edit dialog", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    const resp = await apiRequest.post(
      `/api/projects/${project.id}/tasks/${task.id}/run_configs`,
      {
        data: {
          name: "Editable Config",
          run_config_properties: {
            type: "kiln_agent",
            model_name: "gpt_4o",
            model_provider_name: "openai",
            prompt_id: "simple_prompt_builder",
            structured_output_mode: "default",
          },
        },
      },
    )
    expect(resp.ok(), "POST run_configs").toBeTruthy()
    const runConfig = (await resp.json()) as { id: string }

    await page.goto(
      `/optimize/${project.id}/${task.id}/run_config/${runConfig.id}`,
    )

    await expect(
      page.getByRole("heading", { name: "Run Configuration", exact: true }),
    ).toBeVisible()

    await page.getByRole("button", { name: "Edit" }).click()

    await expect(
      page.getByText("Run Configuration Name", { exact: true }),
    ).toBeVisible()

    // Navigate away to prevent teardown race with page form handlers
    await page.goto("about:blank")
  })

  /* @act
  ## Goals
  The optimize overview page shows run configs in a table when they exist,
  displaying the config name, and the table has sortable column headers.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - First create a run config via API, then navigate to the optimize overview
  - Table shows Name, Prompt, Model, Type, Created At columns
  - Config name appears in the table row

  ## Assertions
  - Table with "Name" column header is visible.
  - Created run config name appears in the table.
  - "No run configurations yet" text is not visible.
  */
  test("optimize overview shows run configs in table", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    const resp = await apiRequest.post(
      `/api/projects/${project.id}/tasks/${task.id}/run_configs`,
      {
        data: {
          name: "My Test Config",
          run_config_properties: {
            type: "kiln_agent",
            model_name: "gpt_4o",
            model_provider_name: "openai",
            prompt_id: "simple_prompt_builder",
            structured_output_mode: "default",
          },
        },
      },
    )
    expect(resp.ok(), "POST run_configs").toBeTruthy()

    await page.goto(`/optimize/${project.id}/${task.id}`)

    await expect(
      page.getByRole("heading", { name: "Optimize", exact: true }),
    ).toBeVisible()

    await expect(page.getByRole("columnheader", { name: "Name" })).toBeVisible()
    await expect(page.getByText("My Test Config")).toBeVisible()
    await expect(page.getByText("No run configurations yet")).not.toBeVisible()
  })
})
