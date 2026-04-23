import { test, expect } from "../../fixtures"

test.describe("Setup project creation", () => {
  /* @act
  ## Goals
  Verify the create project page renders with heading, project name input,
  project description textarea, and the Create Project submit button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /setup/create_project.
  - seededProjectWithTask prevents the root layout redirect to /setup.
  - Project Name input has id="project_name".
  - Project Description textarea has id="project_description".
  - Submit button label is "Create Project".

  ## Assertions
  - The heading "Create a Project" is visible.
  - The project_name input is visible and empty.
  - The project_description textarea is visible and empty.
  - A button with text "Create Project" is visible.
  */
  test("create project page renders form and heading", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/setup/create_project")

    await expect(
      page.getByRole("heading", { name: "Create a Project" }),
    ).toBeVisible()
    await expect(page.locator("#project_name")).toBeVisible()
    await expect(page.locator("#project_name")).toHaveValue("")
    await expect(page.locator("#project_description")).toBeVisible()
    await expect(page.locator("#project_description")).toHaveValue("")
    await expect(
      page.getByRole("button", { name: "Create Project" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Clicking "Create an example" pre-fills the project name and description
  fields with example values.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The link text is "Create an example" and it is a button element.
  - After clicking, project_name should be "Example Project".
  - After clicking, project_description should contain "example project".

  ## Assertions
  - The project_name input has value "Example Project".
  - The project_description textarea is not empty.
  */
  test("create project example button pre-fills form", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/setup/create_project")
    await expect(page.locator("#project_name")).toHaveValue("")

    await page.getByRole("button", { name: "Create an example" }).click()

    await expect(page.locator("#project_name")).toHaveValue("Example Project")
    await expect(page.locator("#project_description")).not.toHaveValue("")
  })

  /* @act
  ## Goals
  Filling in a project name and clicking "Create Project" creates the project
  via the API and redirects to the create task page.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest

  ## Hints
  - After successful creation, the page redirects to /setup/create_task/<project_id>.
  - The URL will match the pattern /setup/create_task/.

  ## Assertions
  - After submit, the URL contains /setup/create_task/.
  - The created project exists in the API response from GET /api/projects.
  */
  test("create project submits and redirects to create task", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/setup/create_project")
    await expect(page.locator("#project_name")).toBeVisible()

    const projectName = "E2E Test Project"
    await page.locator("#project_name").fill(projectName)

    await page.getByRole("button", { name: "Create Project" }).click()

    await expect(page).toHaveURL(/\/setup\/create_task\//)

    const resp = await apiRequest.get("/api/projects")
    expect(resp.ok()).toBeTruthy()
    const projects = (await resp.json()) as Array<{ name: string }>
    expect(projects.some((p) => p.name === projectName)).toBeTruthy()
  })

  /* @act
  ## Goals
  The create project page shows an "import an existing project" link that
  navigates to the import project setup page.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The link text is "import an existing project".
  - The href is /setup/import_project.

  ## Assertions
  - A link with text "import an existing project" is visible.
  - The link href is /setup/import_project.
  */
  test("create project has import link", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/setup/create_project")

    const importLink = page.getByRole("link", {
      name: "import an existing project",
    })
    await expect(importLink).toBeVisible()
    await expect(importLink).toHaveAttribute("href", "/setup/import_project")
  })

  /* @act
  ## Goals
  Verify the create task page renders with heading, task name input,
  task instructions textarea, and the Create Task submit button. In onboarding
  mode, advanced fields like thinking instructions should be hidden.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest

  ## Hints
  - Uses the seeded project ID for the create_task route.
  - Route is /setup/create_task/<project_id>.
  - Task Name input has id="task_name".
  - Task Instructions textarea has id="task_instructions".
  - Submit button label is "Create Task".
  - Thinking instructions (id="thinking_instructions") should not be visible in onboarding mode.

  ## Assertions
  - The heading "Create a Task" is visible.
  - The task_name input is visible and empty.
  - The task_instructions textarea is visible and empty.
  - A button with text "Create Task" is visible.
  - The thinking_instructions field is not visible.
  */
  test("create task page renders form in onboarding mode", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/setup/create_task/${project.id}`)

    await expect(
      page.getByRole("heading", { name: "Create a Task" }),
    ).toBeVisible()
    await expect(page.locator("#task_name")).toBeVisible()
    await expect(page.locator("#task_name")).toHaveValue("")
    await expect(page.locator("#task_instructions")).toBeVisible()
    await expect(page.locator("#task_instructions")).toHaveValue("")
    await expect(
      page.getByRole("button", { name: "Create Task" }),
    ).toBeVisible()
    await expect(page.locator("#thinking_instructions")).not.toBeVisible()
  })

  /* @act
  ## Goals
  Clicking "Try an example." on the create task page pre-fills the task name
  and instructions with example values (Joke Generator).

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The link text is "Try an example." and it is a button element.
  - After clicking, task_name should be "Joke Generator".
  - After clicking, task_instructions should contain content about generating jokes.

  ## Assertions
  - The task_name input has value "Joke Generator".
  - The task_instructions textarea is not empty.
  */
  test("create task example button pre-fills form", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/setup/create_task/${project.id}`)
    await expect(page.locator("#task_name")).toHaveValue("")

    await page.getByRole("button", { name: "Try an example." }).click()

    await expect(page.locator("#task_name")).toHaveValue("Joke Generator")
    await expect(page.locator("#task_instructions")).not.toHaveValue("")
  })

  /* @act
  ## Goals
  Filling in a task name and instructions then clicking "Create Task" creates
  the task and redirects to the home page.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest

  ## Hints
  - After successful creation, the page redirects to / which then redirects to /run.
  - The task should appear in GET /api/projects/:pid/tasks.

  ## Assertions
  - After submit, the URL is /run (home page).
  - The created task exists in the API.
  */
  test("create task submits and redirects home", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/setup/create_task/${project.id}`)
    await expect(page.locator("#task_name")).toBeVisible()

    const taskName = "E2E Test Task"
    await page.locator("#task_name").fill(taskName)
    await page
      .locator("#task_instructions")
      .fill("Test instruction for E2E task.")

    await page.getByRole("button", { name: "Create Task" }).click()

    await expect(page).toHaveURL("/run")

    const tasksResp = await apiRequest.get(
      `/api/projects/${encodeURIComponent(project.id)}/tasks`,
    )
    expect(tasksResp.ok()).toBeTruthy()
    const tasks = (await tasksResp.json()) as Array<{ name: string }>
    expect(tasks.some((t) => t.name === taskName)).toBeTruthy()
  })

  /* @act
  ## Goals
  Verify the select task page renders with heading and shows the projects and
  tasks panels. When a seeded project with a task exists, the project appears
  in the projects list and the task appears in the tasks list.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /setup/select_task.
  - The page has a Projects section header and a Tasks section header.
  - The seeded project name should appear as a button in the projects panel.
  - The seeded task name should appear in the tasks panel.
  - Use getByRole for project name to avoid strict mode violations (name appears multiple times).

  ## Assertions
  - The heading "Select a Task" is visible.
  - A button containing the seeded project name is visible.
  - The seeded task name is visible in the tasks panel.
  */
  test("select task page renders project and task lists", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto("/setup/select_task")

    await expect(
      page.getByRole("heading", { name: "Select a Task" }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: new RegExp(project.name) }),
    ).toBeVisible()
    await expect(page.getByText(task.name)).toBeVisible()
  })

  /* @act
  ## Goals
  Clicking a task in the select task page sets it as the current task and
  navigates to the home page.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Click the task name button in the tasks panel.
  - After clicking, the URL should be /run (home page after / redirect).

  ## Assertions
  - After clicking the task, the URL is /run.
  */
  test("select task page selects task and navigates home", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { task } = seededProjectWithTask

    await page.goto("/setup/select_task")
    await expect(page.getByText(task.name)).toBeVisible()

    await page.getByRole("button", { name: task.name }).click()

    await expect(page).toHaveURL("/run")
  })

  /* @act
  ## Goals
  The select task page shows a "+ New Project" link that navigates to the
  create project setup page and a "+ New Task" link.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The "+ New Project" link has href /setup/create_project.
  - The "+ New Task" link has href starting with /setup/create_task/.

  ## Assertions
  - A link with text "+ New Project" is visible with href /setup/create_project.
  - A link with text "+ New Task" is visible.
  */
  test("select task page has new project and new task links", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/setup/select_task")

    const newProjectLink = page.getByRole("link", { name: "+ New Project" })
    await expect(newProjectLink).toBeVisible()
    await expect(newProjectLink).toHaveAttribute(
      "href",
      "/setup/create_project",
    )

    const newTaskLink = page.getByRole("link", { name: "+ New Task" })
    await expect(newTaskLink).toBeVisible()
  })

  /* @act
  ## Goals
  Verify the import project page renders with heading and shows the two import
  method options: Import from Local Folder and Git Auto Sync.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /setup/import_project.
  - seededProjectWithTask prevents the root layout redirect to /setup.
  - The two method buttons contain "Import from Local Folder" and "Git Auto Sync".
  - There is also a "create a new project" link.

  ## Assertions
  - The heading "Import Project" is visible.
  - A button containing "Import from Local Folder" is visible.
  - A button containing "Git Auto Sync" is visible.
  - A link with text "create a new project" is visible.
  */
  test("import project page renders method selection", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/setup/import_project")

    await expect(
      page.getByRole("heading", { name: "Import Project" }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: /Import from Local Folder/ }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: /Git Auto Sync/ }),
    ).toBeVisible()
    await expect(
      page.getByRole("link", { name: "create a new project" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Clicking "Import from Local Folder" on the import project page shows the
  local file import form with a file path input or a select file button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - After clicking the local folder method, the page shows either a "Select Project File"
    button or an "Existing Project Path" input (id="import_project_path") depending on
    whether the file selector API is available.
  - The page text mentions "Select or enter the path to a project.kiln file".

  ## Assertions
  - After clicking, the text about selecting a project.kiln file is visible.
  */
  test("import project local folder shows file import UI", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/setup/import_project")

    await page.getByRole("button", { name: /Import from Local Folder/ }).click()

    await expect(
      page.getByText("Select or enter the path to a project.kiln file"),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The "create a new project" link on the import project page navigates to
  the create project setup page.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The link href is /setup/create_project.

  ## Assertions
  - The link with text "create a new project" has href /setup/create_project.
  */
  test("import project has create new project link", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/setup/import_project")

    const createLink = page.getByRole("link", {
      name: "create a new project",
    })
    await expect(createLink).toBeVisible()
    await expect(createLink).toHaveAttribute("href", "/setup/create_project")
  })
})
