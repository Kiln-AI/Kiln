import { test, expect } from "../../fixtures"

test.describe("RAG configs list page", () => {
  /* @act
  ## Goals
  When no RAG configs exist, the list page shows an empty state with a
  "Create Search Tool" intro and a primary action button linking to the
  add_search_tool route.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /docs/rag_configs/{project_id}.
  - Empty state renders EmptyRagConfigsIntro which shows "Create a Search Tool" heading
    and a "Create Search Tool" button linking to /docs/rag_configs/{project_id}/add_search_tool.

  ## Assertions
  - The text "Create a Search Tool" is visible.
  - The "Create Search Tool" link points to the add_search_tool route.
  - No table is present on the page.
  */
  test("shows empty state when no RAG configs exist", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/rag_configs/${project.id}`)

    await expect(page.getByText("Create a Search Tool")).toBeVisible()

    const createLink = page.getByRole("link", {
      name: "Create Search Tool",
    })
    await expect(createLink).toHaveAttribute(
      "href",
      `/docs/rag_configs/${project.id}/add_search_tool`,
    )

    await expect(page.locator("table")).not.toBeVisible()
  })

  /* @act
  ## Goals
  The RAG configs list page renders the correct title, subtitle, and breadcrumbs
  linking to Optimize and Docs & Search.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Page title is "Search Tools (RAG)".
  - Breadcrumbs include "Optimize" and "Docs & Search".

  ## Assertions
  - The heading "Search Tools (RAG)" is visible.
  - The breadcrumb "Docs & Search" links to /docs/{project_id}.
  */
  test("shows page title and breadcrumbs", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/docs/rag_configs/${project.id}`)

    await expect(
      page.getByRole("heading", { name: "Search Tools (RAG)" }),
    ).toBeVisible()

    const breadcrumbs = page.locator(".breadcrumbs")

    await expect(
      breadcrumbs.getByRole("link", { name: "Docs & Search" }),
    ).toHaveAttribute("href", `/docs/${project.id}`)

    await expect(
      breadcrumbs.getByRole("link", { name: "Optimize" }),
    ).toHaveAttribute("href", `/optimize/${project.id}/${task.id}`)
  })

  /* @act
  ## Goals
  The empty state description text mentions allowing tasks to search documents
  (RAG), providing context about what search tools do.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The subtitle reads "Enable tasks to search documents for knowledge."
  - The empty intro has text about searching knowledge in documents.

  ## Assertions
  - The subtitle text "Enable tasks to search documents for knowledge" is visible.
  */
  test("shows subtitle description", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/rag_configs/${project.id}`)

    await expect(
      page.getByText("Enable tasks to search documents for knowledge"),
    ).toBeVisible()
  })
})

test.describe("Create RAG config page", () => {
  /* @act
  ## Goals
  The create RAG config page renders the form with Part 1: Tool Properties
  including the Search Tool Name and Search Tool Description fields.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /docs/rag_configs/{project_id}/create_rag_config.
  - The form has id="tool_name" for the name input and id="tool_description" for the textarea.
  - Part 1 heading reads "Part 1: Tool Properties".

  ## Assertions
  - The heading "Create Search Tool (RAG)" is visible.
  - The "Part 1: Tool Properties" section heading is visible.
  - The tool_name input field is present.
  - The tool_description textarea is present.
  */
  test("renders form with tool properties section", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/rag_configs/${project.id}/create_rag_config`)

    await expect(
      page.getByRole("heading", { name: "Create Search Tool (RAG)" }),
    ).toBeVisible()

    await expect(page.getByText("Part 1: Tool Properties")).toBeVisible()

    await expect(page.locator("#tool_name")).toBeVisible()
    await expect(page.locator("#tool_description")).toBeVisible()
  })

  /* @act
  ## Goals
  The create RAG config form renders Part 2: Search Configuration with
  sub-config selector dropdowns for Extractor, Chunker, Embedding Model,
  Search Index, and Reranker.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Part 2 heading reads "Part 2: Search Configuration".
  - Selectors have ids: extractor_select, chunker_select, embedding_select,
    vector_store_select, reranker_select.

  ## Assertions
  - The "Part 2: Search Configuration" section heading is visible.
  - Labels for Extractor, Chunker, Embedding Model, Search Index, and Reranker are visible.
  */
  test("renders search configuration section with sub-config selectors", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/rag_configs/${project.id}/create_rag_config`)

    await expect(page.getByText("Part 2: Search Configuration")).toBeVisible()

    for (const label of [
      "Extractor",
      "Chunker",
      "Embedding Model",
      "Search Index",
      "Reranker",
    ]) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
    }
  })

  /* @act
  ## Goals
  The create RAG config page shows correct breadcrumbs linking back through
  the navigation hierarchy.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Breadcrumbs: Optimize, Docs & Search, Search Tools, Add Search Tool.
  - "Search Tools" links to /docs/rag_configs/{project_id}.
  - "Docs & Search" links to /docs/{project_id}.

  ## Assertions
  - The "Search Tools" breadcrumb links to /docs/rag_configs/{project_id}.
  - The "Docs & Search" breadcrumb links to /docs/{project_id}.
  */
  test("shows breadcrumbs with correct links", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/rag_configs/${project.id}/create_rag_config`)

    const breadcrumbs = page.locator(".breadcrumbs")

    await expect(
      breadcrumbs.getByRole("link", { name: "Search Tools" }),
    ).toHaveAttribute("href", `/docs/rag_configs/${project.id}`)

    await expect(
      breadcrumbs.getByRole("link", { name: "Docs & Search" }),
    ).toHaveAttribute("href", `/docs/${project.id}`)
  })

  /* @act
  ## Goals
  The form has a "Create Search Tool" submit button that is visible and
  the form shows an Advanced Options collapsible section with Reference Name
  and Reference Description fields.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Submit button label is "Create Search Tool" from FormContainer.
  - Advanced Options is a Collapse component with fields rag_config_name and rag_config_description.

  ## Assertions
  - A "Create Search Tool" button is visible.
  - An "Advanced Options" section is present on the page.
  */
  test("shows submit button and advanced options section", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/rag_configs/${project.id}/create_rag_config`)

    await expect(
      page.getByRole("button", { name: "Create Search Tool" }),
    ).toBeVisible()

    await expect(page.getByText("Advanced Options").first()).toBeVisible()
  })
})

test.describe("RAG config detail page", () => {
  /* @act
  ## Goals
  When navigating to a non-existent RAG config ID, the detail page shows
  a "not found" error state.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /docs/rag_configs/{project_id}/{rag_config_id}/rag_config.
  - With a fake ID, the API returns an error and the page shows the error or
    "Search Tool configuration not found" text.

  ## Assertions
  - The error or "not found" message is visible on the page.
  */
  test("shows error for non-existent config", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/rag_configs/${project.id}/fake-rag-id/rag_config`)

    // The page will show either an API error or a "not found" message
    await expect(
      page
        .getByText("Search Tool configuration not found")
        .or(page.locator(".text-error")),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The RAG config detail page shows the correct title and breadcrumbs
  linking to Search Tools, Docs & Search, and Optimize.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Page title heading is "Search Tool (RAG)".
  - Breadcrumbs: Optimize, Docs & Search, Search Tools.
  - "Search Tools" links to /docs/rag_configs/{project_id}.

  ## Assertions
  - The heading "Search Tool (RAG)" is visible.
  - The "Search Tools" breadcrumb links to /docs/rag_configs/{project_id}.
  */
  test("shows page title and breadcrumbs", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    // Navigate to a non-existent config to at least verify the page shell renders
    await page.goto(`/docs/rag_configs/${project.id}/fake-rag-id/rag_config`)

    await expect(
      page.getByRole("heading", { name: "Search Tool (RAG)" }),
    ).toBeVisible()

    const breadcrumbs = page.locator(".breadcrumbs")
    await expect(
      breadcrumbs.getByRole("link", { name: "Search Tools" }),
    ).toHaveAttribute("href", `/docs/rag_configs/${project.id}`)
  })
})

test.describe("Clone RAG config page", () => {
  /* @act
  ## Goals
  When navigating to clone a non-existent RAG config, the page shows an
  error state indicating the search tool was not found.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /docs/rag_configs/{project_id}/{rag_config_id}/rag_config/clone.
  - With a fake ID, shows "Search Tool not found" in red text.

  ## Assertions
  - The error text "Search Tool not found" is visible.
  */
  test("shows error for non-existent config", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(
      `/docs/rag_configs/${project.id}/fake-rag-id/rag_config/clone`,
    )

    await expect(page.locator(".text-red-500").first()).toBeVisible()
  })

  /* @act
  ## Goals
  The clone page shows the correct title and breadcrumbs.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Page title is "Clone Search Tool (RAG)".
  - Breadcrumbs include "Search Tools" linking to /docs/rag_configs/{project_id}.

  ## Assertions
  - The heading "Clone Search Tool (RAG)" is visible.
  - The "Search Tools" breadcrumb links to /docs/rag_configs/{project_id}.
  */
  test("shows page title and breadcrumbs", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(
      `/docs/rag_configs/${project.id}/fake-rag-id/rag_config/clone`,
    )

    await expect(
      page.getByRole("heading", { name: "Clone Search Tool (RAG)" }),
    ).toBeVisible()

    const breadcrumbs = page.locator(".breadcrumbs")
    await expect(
      breadcrumbs.getByRole("link", { name: "Search Tools" }),
    ).toHaveAttribute("href", `/docs/rag_configs/${project.id}`)
  })
})
