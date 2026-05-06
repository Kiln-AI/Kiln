import { test, expect } from "../../fixtures"

test.describe("Tools management", () => {
  /* @act
  ## Goals
  The tools overview page loads and shows the empty state when no tools exist,
  including the intro title and description about adding tools to a project.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}
  - Empty state shows "Add Tools to Your Project" title via Intro component
  - Two description paragraphs about tool capabilities
  - "Add Tool" link/button visible in empty state

  ## Assertions
  - Page heading "Tools" is visible.
  - "Add Tools to Your Project" text is visible.
  - "Add Tool" link is visible in the empty state.
  */
  test("tools overview page shows empty state", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}`)

    await expect(
      page.getByRole("heading", { name: "Tools", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Add Tools to Your Project")).toBeVisible()

    await expect(page.getByRole("link", { name: "Add Tool" })).toBeVisible()
  })

  /* @act
  ## Goals
  The add tools page loads and displays the suggested tools carousel and the
  custom tools section with all four custom tool options.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/add_tools
  - Page heading is "Add Tools"
  - "Suggested Tools" heading visible
  - "Custom Tools" section visible with four items: Search Tools (RAG),
    Kiln Task as Tool, Remote MCP Servers, Local MCP Servers
  - Breadcrumbs include "Tools"

  ## Assertions
  - Page heading "Add Tools" is visible.
  - "Suggested Tools" heading is visible.
  - "Custom Tools" heading is visible.
  - "Search Tools (RAG)" text is visible.
  - "Remote MCP Servers" text is visible.
  - "Local MCP Servers" text is visible.
  - "Kiln Task as Tool" text is visible.
  */
  test("add tools page shows suggested and custom tools", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}/add_tools`)

    await expect(
      page.getByRole("heading", { name: "Add Tools", exact: true }),
    ).toBeVisible()

    await expect(
      page.getByRole("heading", { name: "Suggested Tools" }),
    ).toBeVisible()

    await expect(
      page.getByRole("heading", { name: "Custom Tools" }),
    ).toBeVisible()

    await expect(page.getByText("Search Tools (RAG)").first()).toBeVisible()
    await expect(page.getByText("Kiln Task as Tool").first()).toBeVisible()
    await expect(page.getByText("Remote MCP Servers").first()).toBeVisible()
    await expect(page.getByText("Local MCP Servers").first()).toBeVisible()
  })

  /* @act
  ## Goals
  The local MCP server page loads and displays the form with all required
  fields: Name, Description, Command, Arguments, and the Environment Variables
  section, plus the Connect submit button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/add_tools/local_mcp
  - Page heading is "Connect Local MCP Server"
  - Form fields: #name, #mcp_description, #command, #args
  - Environment Variables section header visible
  - Submit button label is "Connect"

  ## Assertions
  - Page heading "Connect Local MCP Server" is visible.
  - Name input (#name) is visible.
  - Description textarea (#mcp_description) is visible.
  - Command input (#command) is visible.
  - Arguments textarea (#args) is visible.
  - "Environment Variables" text is visible.
  - "Connect" submit button is visible.
  */
  test("local mcp page shows form fields", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}/add_tools/local_mcp`)

    await expect(
      page.getByRole("heading", {
        name: "Connect Local MCP Server",
        exact: true,
      }),
    ).toBeVisible()

    await expect(page.locator("#name")).toBeVisible()
    await expect(page.locator("#mcp_description")).toBeVisible()
    await expect(page.locator("#command")).toBeVisible()
    await expect(page.locator("#args")).toBeVisible()

    await expect(
      page.getByText("Environment Variables", { exact: true }),
    ).toBeVisible()

    await expect(page.getByRole("button", { name: /^Connect/ })).toBeVisible()
  })

  /* @act
  ## Goals
  The remote MCP server page loads and displays the form with all required
  fields: Name, Description, Server URL, and the Headers section, plus the
  Connect submit button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/add_tools/remote_mcp
  - Page heading is "Connect Remote MCP Server"
  - Form fields: #name, #mcp_description, #mcp_server_url
  - Headers section header visible
  - Submit button label is "Connect"

  ## Assertions
  - Page heading "Connect Remote MCP Server" is visible.
  - Name input (#name) is visible.
  - Description textarea (#mcp_description) is visible.
  - Server URL input (#mcp_server_url) is visible.
  - "Headers" text is visible.
  - "Connect" submit button is visible.
  */
  test("remote mcp page shows form fields", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}/add_tools/remote_mcp`)

    await expect(
      page.getByRole("heading", {
        name: "Connect Remote MCP Server",
        exact: true,
      }),
    ).toBeVisible()

    await expect(page.locator("#name")).toBeVisible()
    await expect(page.locator("#mcp_description")).toBeVisible()
    await expect(page.locator("#mcp_server_url")).toBeVisible()

    await expect(
      page.getByText("Headers", { exact: true }).first(),
    ).toBeVisible()

    await expect(page.getByRole("button", { name: /^Connect/ })).toBeVisible()
  })

  /* @act
  ## Goals
  Navigating from the empty tools overview page to the add tools page works
  via the "Add Tool" link in the empty state.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Start at /tools/{project_id} which shows empty state
  - Click "Add Tool" link
  - Should navigate to /tools/{project_id}/add_tools

  ## Assertions
  - After clicking "Add Tool", URL contains /add_tools.
  - "Add Tools" heading is visible on the destination page.
  */
  test("empty state add tool link navigates to add tools page", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}`)

    await expect(page.getByText("Add Tools to Your Project")).toBeVisible()

    await page.getByRole("link", { name: "Add Tool" }).click()

    await page.waitForURL(`**/tools/${project.id}/add_tools`)

    await expect(
      page.getByRole("heading", { name: "Add Tools", exact: true }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The local MCP form has an "Add Environment Variable" button that adds a new
  environment variable row with Name, Value, and Secret fields.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/add_tools/local_mcp
  - Initially shows "No Environment Variables" text
  - Click "Add Environment Variable" button to add a row
  - New row contains env_var_name_0, env_var_value_0, secret_0 fields

  ## Assertions
  - "No Environment Variables" text is visible initially.
  - After clicking add, env var name field is visible.
  - After clicking add, env var value field is visible.
  */
  test("local mcp form add environment variable row", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}/add_tools/local_mcp`)

    await expect(page.getByText("No Environment Variables")).toBeVisible()

    await page.getByRole("button", { name: "Add Environment Variable" }).click()

    await expect(page.locator("#env_var_name_0")).toBeVisible()
    await expect(page.locator("#env_var_value_0")).toBeVisible()
  })

  /* @act
  ## Goals
  The remote MCP form has an "Add Header" button that adds a new header row
  with Header Name, Value, and Secret fields.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /tools/{project_id}/add_tools/remote_mcp
  - Initially shows "No Headers" text
  - Click "Add Header" button to add a row
  - New row contains header_name_0, header_value_0, secret_0 fields

  ## Assertions
  - "No Headers" text is visible initially.
  - After clicking add, header name field is visible.
  - After clicking add, header value field is visible.
  */
  test("remote mcp form add header row", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/tools/${project.id}/add_tools/remote_mcp`)

    await expect(page.getByText("No Headers")).toBeVisible()

    await page.getByRole("button", { name: "Add Header" }).click()

    await expect(page.locator("#header_name_0")).toBeVisible()
    await expect(page.locator("#header_value_0")).toBeVisible()
  })
})
