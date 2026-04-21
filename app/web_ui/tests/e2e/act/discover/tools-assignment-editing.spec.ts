import { test, expect } from "../../fixtures"

test.describe("Tools assignment and editing", () => {
  /* @act
  ## Goals
  The add tool to task page shows an error message when no tool_id query
  parameter is provided.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/add_tool_to_task (no ?tool_id param)
  - Page title is "Add MCP Tool As Run Config"
  - When tool_id is missing, shows "Tool data not available" error text

  ## Assertions
  - Page heading "Add MCP Tool As Run Config" is visible.
  - Error text "Tool data not available" is visible.
  */
  test("add tool to task shows error when tool_id missing", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}/add_tool_to_task`)

    await expect(
      page.getByRole("heading", { name: "Add MCP Tool As Run Config" }),
    ).toBeVisible()

    await expect(page.getByText("Tool data not available")).toBeVisible()
  })

  /* @act
  ## Goals
  The add tool to task page shows a loading spinner and then the form
  structure when a tool_id query parameter is provided, even if the tool
  server does not exist (the API call will fail gracefully).

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/add_tool_to_task?tool_id=mcp::builtin::fake_server::fake_tool
  - Page title is "Add MCP Tool As Run Config"
  - Subtitle contains "Allow one of your existing tasks"
  - "Read the Docs" link visible
  - Breadcrumbs include "Tools"

  ## Assertions
  - Page heading "Add MCP Tool As Run Config" is visible.
  - Subtitle text "Allow one of your existing tasks" is visible.
  - "Read the Docs" link is visible.
  */
  test("add tool to task page renders with tool_id param", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const fakeToolId = "mcp::builtin::fake_server::fake_tool"
    await page.goto(
      `/tools/${project.id}/add_tool_to_task?tool_id=${encodeURIComponent(fakeToolId)}`,
    )

    await expect(
      page.getByRole("heading", { name: "Add MCP Tool As Run Config" }),
    ).toBeVisible()

    await expect(
      page.getByText("Allow one of your existing tasks"),
    ).toBeVisible()

    await expect(
      page.getByRole("link", { name: "Read the Docs" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The edit tool server page shows an error state when navigating with
  an invalid tool_server_id that does not exist.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/edit_tool_server/{tool_server_id}
  - Page title is "Edit Tool Server"
  - With invalid ID, shows "Error Loading Tool Server" text after loading

  ## Assertions
  - Page heading "Edit Tool Server" is visible.
  - "Error Loading Tool Server" text is visible after loading completes.
  */
  test("edit tool server shows error for invalid server id", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(
      `/tools/${project.id}/edit_tool_server/nonexistent_server_id`,
    )

    await expect(
      page.getByRole("heading", { name: "Edit Tool Server" }),
    ).toBeVisible()

    await expect(page.getByText("Error Loading Tool Server")).toBeVisible()
  })

  /* @act
  ## Goals
  The create task from tool page shows an error message when no tool_id
  query parameter is provided.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/create_task_from_tool (no ?tool_id param)
  - Page title is "New Task from Tool"
  - When tool_id is missing, shows "No tool selected" error text

  ## Assertions
  - Page heading "New Task from Tool" is visible.
  - Error text containing "No tool selected" is visible.
  */
  test("create task from tool shows error when tool_id missing", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}/create_task_from_tool`)

    await expect(
      page.getByRole("heading", { name: "New Task from Tool" }),
    ).toBeVisible()

    await expect(page.getByText("No tool selected")).toBeVisible()
  })

  /* @act
  ## Goals
  The create task from tool page shows the page structure with title,
  subtitle link, and breadcrumbs when a tool_id is provided. Since the
  tool server does not exist, it shows an error about loading tool details.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/create_task_from_tool?tool_id=mcp::builtin::fake_server::fake_tool
  - Page title is "New Task from Tool"
  - "Read the Docs" link visible in subtitle
  - With invalid tool_id, shows error about failing to load tool data
  - Breadcrumbs include "Tools"

  ## Assertions
  - Page heading "New Task from Tool" is visible.
  - "Read the Docs" link is visible.
  - Error text about loading failure is visible.
  */
  test("create task from tool page renders with invalid tool_id", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const fakeToolId = "mcp::builtin::fake_server::fake_tool"
    await page.goto(
      `/tools/${project.id}/create_task_from_tool?tool_id=${encodeURIComponent(fakeToolId)}`,
    )

    await expect(
      page.getByRole("heading", { name: "New Task from Tool" }),
    ).toBeVisible()

    await expect(
      page.getByRole("link", { name: "Read the Docs" }),
    ).toBeVisible()

    await expect(page.getByText("Failed to load tool server")).toBeVisible()
  })
})
