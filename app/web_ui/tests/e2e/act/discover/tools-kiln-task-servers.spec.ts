import { test, expect } from "../../fixtures"

test.describe("Tools - Kiln task tools and servers", () => {
  /* @act
  ## Goals
  The Kiln task tools list page shows an empty state when no tools exist,
  including the title, subtitle, Create New button, and empty-state message.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/kiln_task_tools
  - Title is "Manage Kiln Tasks as Tools"
  - Subtitle is "Allow your tasks to call another Kiln task, as a tool call."
  - Empty state shows "No Kiln Task Tools" heading
  - "Create New" action button links to add_tools/kiln_task

  ## Assertions
  - Page heading "Manage Kiln Tasks as Tools" is visible.
  - "No Kiln Task Tools" text is visible.
  - "Create New" link is visible.
  */
  test("kiln task tools list shows empty state", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}/kiln_task_tools`)

    await expect(
      page.getByRole("heading", {
        name: "Manage Kiln Tasks as Tools",
        exact: true,
      }),
    ).toBeVisible()

    await expect(page.getByText("No Kiln Task Tools")).toBeVisible()

    await expect(page.getByRole("button", { name: "Create New" })).toBeVisible()
  })

  /* @act
  ## Goals
  The add Kiln task tool page loads and shows the form with the task selector
  and the submit button. The Tool Name and Tool Description fields should
  appear only after a task is selected.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/add_tools/kiln_task
  - Page title is "Create Tool from Kiln Task"
  - Subtitle is "Allow your tasks to call another Kiln task, as a tool call."
  - Form has a "Kiln Task" fancy select dropdown
  - After selecting a task, Tool Name (#task_name) and Tool Description (#task_description) fields appear
  - Submit button label is "Add"

  ## Assertions
  - Page heading "Create Tool from Kiln Task" is visible.
  - "Add" submit button is visible.
  - The Kiln Task label is visible.
  */
  test("add kiln task tool page loads with form", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}/add_tools/kiln_task`)

    await expect(
      page.getByRole("heading", {
        name: "Create Tool from Kiln Task",
        exact: true,
      }),
    ).toBeVisible()

    await expect(page.getByText("Kiln Task", { exact: true })).toBeVisible()

    await expect(page.getByRole("button", { name: "Add" })).toBeVisible()
  })

  /* @act
  ## Goals
  Submitting the add Kiln task tool form without selecting a task shows a
  validation error message.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/add_tools/kiln_task
  - Click "Add" without selecting a task
  - Error message "Please select a task." appears

  ## Assertions
  - After clicking Add with no task selected, "Please select a task." error is visible.
  */
  test("add kiln task tool validates required task", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}/add_tools/kiln_task`)

    await expect(page.getByRole("button", { name: "Add" })).toBeVisible()

    await page.getByRole("button", { name: "Add" }).click()

    await expect(page.getByText("Please select a task.")).toBeVisible()
  })

  /* @act
  ## Goals
  The Kiln task tool detail page loads for an API-seeded tool and shows
  tool properties (ID, Tool Name, Tool Description) and task properties.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a kiln task tool via POST)

  ## Hints
  - First create a run config via POST /api/projects/{project_id}/tasks/{task_id}/run_configs
  - Then seed a kiln task tool via POST /api/projects/{project_id}/kiln_task_tool
  - Route is /tools/{project_id}/kiln_task/{tool_server_id}
  - Page title is "Kiln Task as Tool"
  - Subtitle shows "Name: {tool_name}"
  - Tool Properties section shows ID, Tool Name, Tool Description
  - Task Properties section shows task info
  - "Clone" and "Archive" action buttons are visible

  ## Assertions
  - Page heading "Kiln Task as Tool" is visible.
  - Tool name is visible in subtitle.
  - "Tool Properties" section heading is visible.
  - "Task Properties" section heading is visible.
  - "Clone" button is visible.
  - "Archive" button is visible.
  */
  test("kiln task tool detail shows properties", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    // Create a run config for the task
    const rcResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/run_configs`,
      {
        data: {
          name: "test-run-config",
          run_config_properties: {
            type: "kiln_agent",
            model_name: "gpt-4o",
            model_provider_name: "openai",
            prompt_id: "simple_prompt_builder",
            structured_output_mode: "default",
          },
        },
      },
    )
    expect(rcResp.ok()).toBeTruthy()
    const runConfig = (await rcResp.json()) as { id: string }

    // Create a kiln task tool
    const toolResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/kiln_task_tool`,
      {
        data: {
          name: "test_tool",
          description: "A test tool description",
          task_id: task.id,
          run_config_id: runConfig.id,
          is_archived: false,
        },
      },
    )
    expect(toolResp.ok()).toBeTruthy()
    const tool = (await toolResp.json()) as { id: string }

    await page.goto(`/tools/${project.id}/kiln_task/${tool.id}`)

    await expect(
      page.getByRole("heading", {
        name: "Kiln Task as Tool",
        exact: true,
      }),
    ).toBeVisible()

    await expect(page.getByText("Name: test_tool")).toBeVisible()

    await expect(page.getByText("Tool Properties")).toBeVisible()
    await expect(page.getByText("Task Properties")).toBeVisible()

    await expect(page.getByRole("button", { name: "Clone" })).toBeVisible()

    await expect(page.getByRole("button", { name: "Archive" })).toBeVisible()
  })

  /* @act
  ## Goals
  Archiving a Kiln task tool on the detail page shows the archived warning
  and changes the button to "Unarchive". Unarchiving removes the warning
  and restores the "Archive" button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a kiln task tool via POST)

  ## Hints
  - Seed a run config and kiln task tool via API
  - Navigate to /tools/{project_id}/kiln_task/{tool_server_id}
  - Click "Archive" button
  - Archived state shows warning "This Kiln task tool is archived"
  - Button becomes "Unarchive"
  - Click "Unarchive" to restore

  ## Assertions
  - After archiving, "This Kiln task tool is archived" warning is visible.
  - "Unarchive" button is visible after archiving.
  - After unarchiving, archived warning is not visible.
  - "Archive" button is visible after unarchiving.
  */
  test("kiln task tool detail archive and unarchive", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    // Create a run config for the task
    const rcResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/run_configs`,
      {
        data: {
          name: "archive-test-config",
          run_config_properties: {
            type: "kiln_agent",
            model_name: "gpt-4o",
            model_provider_name: "openai",
            prompt_id: "simple_prompt_builder",
            structured_output_mode: "default",
          },
        },
      },
    )
    expect(rcResp.ok()).toBeTruthy()
    const runConfig = (await rcResp.json()) as { id: string }

    // Create a kiln task tool
    const toolResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/kiln_task_tool`,
      {
        data: {
          name: "archive_test_tool",
          description: "Tool for archive testing",
          task_id: task.id,
          run_config_id: runConfig.id,
          is_archived: false,
        },
      },
    )
    expect(toolResp.ok()).toBeTruthy()
    const tool = (await toolResp.json()) as { id: string }

    await page.goto(`/tools/${project.id}/kiln_task/${tool.id}`)

    await expect(
      page.getByRole("heading", {
        name: "Kiln Task as Tool",
        exact: true,
      }),
    ).toBeVisible()

    await page.getByRole("button", { name: "Archive" }).click()

    await expect(
      page.getByText("This Kiln task tool is archived"),
    ).toBeVisible()

    await expect(page.getByRole("button", { name: "Unarchive" })).toBeVisible()

    await page.getByRole("button", { name: "Unarchive" }).click()

    await expect(
      page.getByText("This Kiln task tool is archived"),
    ).not.toBeVisible()

    await expect(page.getByRole("button", { name: "Archive" })).toBeVisible()
  })

  /* @act
  ## Goals
  The Kiln task tools list page shows tools in a table after creating one
  via API, with tool name, description, status columns.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a kiln task tool)

  ## Hints
  - Seed a run config and kiln task tool via API
  - Route is /tools/{project_id}/kiln_task_tools
  - Table has columns: Tool Name, Description, Created At, Status
  - Active tool shows "Ready" status
  - Tool name in table is clickable

  ## Assertions
  - Tool name "list_test_tool" is visible in the table.
  - "Ready" status indicator is visible.
  - Table column headers are visible.
  */
  test("kiln task tools list shows seeded tools", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    // Create a run config for the task
    const rcResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/run_configs`,
      {
        data: {
          name: "list-test-config",
          run_config_properties: {
            type: "kiln_agent",
            model_name: "gpt-4o",
            model_provider_name: "openai",
            prompt_id: "simple_prompt_builder",
            structured_output_mode: "default",
          },
        },
      },
    )
    expect(rcResp.ok()).toBeTruthy()
    const runConfig = (await rcResp.json()) as { id: string }

    // Create a kiln task tool
    const toolResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/kiln_task_tool`,
      {
        data: {
          name: "list_test_tool",
          description: "A tool for list testing",
          task_id: task.id,
          run_config_id: runConfig.id,
          is_archived: false,
        },
      },
    )
    expect(toolResp.ok()).toBeTruthy()

    await page.goto(`/tools/${project.id}/kiln_task_tools`)

    await expect(
      page.getByRole("heading", {
        name: "Manage Kiln Tasks as Tools",
        exact: true,
      }),
    ).toBeVisible()

    await expect(
      page.getByRole("columnheader", { name: "Tool Name" }),
    ).toBeVisible()
    await expect(
      page.getByRole("columnheader", { name: "Description" }),
    ).toBeVisible()
    await expect(
      page.getByRole("columnheader", { name: "Status" }),
    ).toBeVisible()

    await expect(page.getByText("list_test_tool")).toBeVisible()
    await expect(page.getByText("Ready")).toBeVisible()
  })

  /* @act
  ## Goals
  The tool server detail page shows an error state when the tool server ID
  does not correspond to a valid, reachable server. The error details block
  and troubleshooting steps should be visible.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/tool_servers/{tool_server_id}
  - With a nonexistent tool_server_id, shows error state
  - Page title is "Tool Server"
  - Error state shows "Tool Not Found" or error loading message

  ## Assertions
  - Page heading "Tool Server" is visible.
  - An error or not-found state is displayed.
  */
  test("tool server detail shows error for invalid server", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}/tool_servers/nonexistent-id`)

    await expect(
      page.getByRole("heading", {
        name: "Tool Server",
        exact: true,
      }),
    ).toBeVisible()

    // Should show either error loading or tool not found
    await expect(
      page
        .getByText("Error Loading Tool Server")
        .or(page.getByText("Tool Not Found")),
    ).toBeVisible()
  })
})
