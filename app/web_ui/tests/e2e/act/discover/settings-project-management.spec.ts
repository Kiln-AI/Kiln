import { test, expect } from "../../fixtures"

test.describe("Settings - project management", () => {
  /* @act
  ## Goals
  The main settings page loads and displays its four category sections:
  Workspace, Models & Providers, Application, and About — along with their
  setting rows. The page was redesigned with denser KilnSettingsRow rows
  grouped under section headers; "Manage Projects" is now folded into the
  Workspace section rather than being its own section.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /settings.
  - Page title heading is "Settings" (h1 from AppPage).
  - Section headings are h2 with exact text: "Workspace", "Models & Providers",
    "Application", "About".
  - Each row is a KilnSettingsRow. Rows render their label inside a styled
    <span>, NOT a <h*> element, so use getByText(...) to assert row labels
    rather than getByRole("heading", ...).
  - Workspace rows: "Edit Current Task", "Edit Current Project", "Manage Projects".
  - Models & Providers rows: "AI Providers", "Custom Models".
  - Application rows: "Application Logs", "Check for Update".
  - About rows: "Docs & Getting Started", "License Agreement".

  ## Assertions
  - Page heading "Settings" is visible.
  - All four section headings are visible.
  - All nine row labels are visible.
  */
  test("settings page loads with all sections", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings")

    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible()

    // Section headings (h2)
    await expect(
      page.getByRole("heading", { name: "Workspace", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("heading", { name: "Models & Providers", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("heading", { name: "Application", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("heading", { name: "About", exact: true }),
    ).toBeVisible()

    // Row labels (rendered as text inside KilnSettingsRow)
    await expect(
      page.getByText("Edit Current Task", { exact: true }),
    ).toBeVisible()
    await expect(
      page.getByText("Edit Current Project", { exact: true }),
    ).toBeVisible()
    await expect(
      page.getByText("Manage Projects", { exact: true }),
    ).toBeVisible()
    await expect(page.getByText("AI Providers", { exact: true })).toBeVisible()
    await expect(page.getByText("Custom Models", { exact: true })).toBeVisible()
    await expect(
      page.getByText("Application Logs", { exact: true }),
    ).toBeVisible()
    await expect(
      page.getByText("Check for Update", { exact: true }),
    ).toBeVisible()
    await expect(
      page.getByText("Docs & Getting Started", { exact: true }),
    ).toBeVisible()
    await expect(
      page.getByText("License Agreement", { exact: true }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The manage projects page loads and displays the seeded project in a table
  with correct column headers and project data.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /settings/manage_projects
  - Page title heading is "Manage Projects" with subtitle "Add or remove projects"
  - Table headers: "Project Name", "Description", "Created At", "Path"
  - Action buttons in header: "Create Project", "Import Project"
  - The seeded project name and description should appear in the table

  ## Assertions
  - Page heading "Manage Projects" is visible.
  - "Add or remove projects" subtitle is visible.
  - "Create Project" button is visible.
  - "Import Project" button is visible.
  - Table column headers are visible.
  - Seeded project name is visible in the table.
  */
  test("manage projects page loads with seeded project", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto("/settings/manage_projects")

    await expect(
      page.getByRole("heading", { name: "Manage Projects", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Add or remove projects")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Create Project" }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Import Project" }),
    ).toBeVisible()

    await expect(
      page.getByRole("columnheader", { name: "Project Name" }),
    ).toBeVisible()
    await expect(
      page.getByRole("columnheader", { name: "Description" }),
    ).toBeVisible()
    await expect(
      page.getByRole("columnheader", { name: "Created At" }),
    ).toBeVisible()
    await expect(page.getByRole("columnheader", { name: "Path" })).toBeVisible()

    await expect(page.getByRole("cell", { name: project.name })).toBeVisible()
  })

  /* @act
  ## Goals
  The manage projects page action menu shows options for Add Task, Edit Project,
  and Remove Project.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /settings/manage_projects
  - Each project row has a TableActionMenu (three-dot menu button)
  - Menu items: "Add Task", "Edit Project", "Remove Project", optionally "Open Folder"
  - Hover the "More options" button to reveal the items (menu uses hover mode)

  ## Assertions
  - The action menu button is visible.
  - After clicking, "Add Task", "Edit Project", "Remove Project" menu items are visible.
  */
  test("manage projects action menu shows options", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings/manage_projects")

    await expect(
      page.getByRole("heading", { name: "Manage Projects", exact: true }),
    ).toBeVisible()

    await page.getByRole("button", { name: "More options" }).hover()

    await expect(page.getByRole("button", { name: "Add Task" })).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Edit Project" }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Remove Project" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The create project page loads with a form containing project name input,
  description textarea, and a Create Project submit button, plus an import link.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /settings/create_project
  - Page title heading is "Add Project"
  - Subtitle: "Projects are a collection of tasks, results, evals, and other resources."
  - Form fields: #project_name (input), #project_description (textarea)
  - Submit button: "Create Project"
  - Import link text: "import an existing project"

  ## Assertions
  - Page heading "Add Project" is visible.
  - Project name input is visible and empty.
  - Project description textarea is visible.
  - "Create Project" submit button is visible.
  - "import an existing project" link is visible.
  */
  test("create project page loads with form", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings/create_project")

    await expect(
      page.getByRole("heading", { name: "Add Project", exact: true }),
    ).toBeVisible()

    await expect(page.locator("#project_name")).toBeVisible()
    await expect(page.locator("#project_name")).toHaveValue("")

    await expect(page.locator("#project_description")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Create Project" }),
    ).toBeVisible()

    await expect(
      page.getByRole("link", { name: "import an existing project" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Creating a new project via the create project form submits successfully
  and redirects to the create task page for the new project.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest

  ## Hints
  - Route is /settings/create_project
  - Fill #project_name with a unique name, optionally fill #project_description
  - Click "Create Project" button
  - On success, redirects to /settings/create_task/{new_project_id}
  - Verify the project exists via GET /api/projects

  ## Assertions
  - After submit, URL changes to /settings/create_task/...
  - The new project appears in the API project list.
  */
  test("create project form submits and redirects", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings/create_project")

    const projectName = `E2E Test Project ${Date.now()}`
    await page.locator("#project_name").fill(projectName)
    await page.locator("#project_description").fill("E2E test description")

    await page.getByRole("button", { name: "Create Project" }).click()

    await page.waitForURL("**/settings/create_task/**")

    await expect
      .poll(async () => {
        const resp = await apiRequest.get("/api/projects")
        if (!resp.ok()) return false
        const projects = (await resp.json()) as Array<{ name: string }>
        return projects.some((p) => p.name === projectName)
      })
      .toBeTruthy()
  })

  /* @act
  ## Goals
  The edit project page loads with the seeded project data pre-populated
  in the form fields.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /settings/edit_project/{project_id}
  - Page title heading is "Edit Project"
  - Form fields: #project_name (pre-populated with project name),
    #project_description (pre-populated with project description)
  - Submit button: "Update Project"
  - Breadcrumb shows "Settings" link

  ## Assertions
  - Page heading "Edit Project" is visible.
  - Project name input has the seeded project name as value.
  - "Update Project" button is visible.
  - "Settings" breadcrumb link is visible.
  */
  test("edit project page loads with existing data", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/settings/edit_project/${project.id}`)

    await expect(
      page.getByRole("heading", { name: "Edit Project", exact: true }),
    ).toBeVisible()

    await expect(page.locator("#project_name")).toHaveValue(project.name)

    await expect(
      page.getByRole("button", { name: "Update Project" }),
    ).toBeVisible()

    await expect(
      page.getByRole("link", { name: "Settings" }).first(),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Editing a project name on the edit project page and saving persists the
  change via the API.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest

  ## Hints
  - Route is /settings/edit_project/{project_id}
  - Clear #project_name and fill with a new name
  - Click "Update Project" button
  - After save, verify via GET /api/projects that the project name was updated

  ## Assertions
  - After save, GET /api/projects returns the updated project name.
  */
  test("edit project page saves changes", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    // Auto-dismiss any beforeunload dialogs triggered during teardown
    page.on("dialog", (dialog) => dialog.accept())

    await page.goto(`/settings/edit_project/${project.id}`)

    await expect(page.locator("#project_name")).toHaveValue(project.name)

    const newName = `Updated Project ${Date.now()}`
    await page.locator("#project_name").fill(newName)

    await page.getByRole("button", { name: "Update Project" }).click()

    await expect
      .poll(async () => {
        const resp = await apiRequest.get("/api/projects")
        if (!resp.ok()) return false
        const projects = (await resp.json()) as Array<{
          id: string
          name: string
        }>
        return projects.some((p) => p.id === project.id && p.name === newName)
      })
      .toBeTruthy()
  })
})
