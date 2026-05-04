import { test, expect } from "../../fixtures"

/**
 * Helper: upload a plain-text document to the project via the bulk API.
 * Returns the created document object (first entry).
 */
async function seedDocument(
  apiRequest: import("@playwright/test").APIRequestContext,
  projectId: string,
  fileName: string,
  content: string,
) {
  const resp = await apiRequest.post(
    `/api/projects/${encodeURIComponent(projectId)}/documents/bulk`,
    {
      multipart: {
        files: {
          name: fileName,
          mimeType: "text/plain",
          buffer: Buffer.from(content, "utf-8"),
        },
      },
    },
  )
  expect(resp.ok(), `seed document ${fileName}`).toBeTruthy()
  const body = await resp.json()
  return body.created_documents[0]
}

test.describe("Docs overview page", () => {
  /* @act
  ## Goals
  The docs overview page renders two feature cards: Document Library and Search Tools (RAG),
  each with a descriptive blurb and an action button linking to the correct sub-page.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /docs/{project_id}.
  - The page title is "Documents & Search".
  - Two cards: "Document Library" with "Manage Documents" button, and "Search Tools (RAG)" with "Manage Search Tools" button.

  ## Assertions
  - Page heading "Documents & Search" is visible.
  - "Manage Documents" link points to /docs/library/{project_id}.
  - "Manage Search Tools" link points to /docs/rag_configs/{project_id}.
  */
  test("renders two feature cards with correct links", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/${project.id}`)

    await expect(
      page.getByRole("heading", { name: "Documents & Search" }),
    ).toBeVisible()

    await expect(
      page.getByRole("heading", { name: "Document Library" }),
    ).toBeVisible()
    await expect(
      page.getByRole("heading", { name: "Search Tools (RAG)" }),
    ).toBeVisible()

    const manageDocsLink = page.getByRole("link", {
      name: "Manage Documents",
    })
    await expect(manageDocsLink).toHaveAttribute(
      "href",
      `/docs/library/${project.id}`,
    )

    const manageSearchLink = page.getByRole("link", {
      name: "Manage Search Tools",
    })
    await expect(manageSearchLink).toHaveAttribute(
      "href",
      `/docs/rag_configs/${project.id}`,
    )
  })

  /* @act
  ## Goals
  The docs overview page shows breadcrumbs including an "Optimize" link.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Breadcrumb "Optimize" links to /optimize/{project_id}/{task_id}.

  ## Assertions
  - An "Optimize" breadcrumb link is visible and points to the correct URL.
  */
  test("shows Optimize breadcrumb", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/docs/${project.id}`)

    const breadcrumb = page
      .locator(".breadcrumbs")
      .getByRole("link", { name: "Optimize" })
    await expect(breadcrumb).toHaveAttribute(
      "href",
      `/optimize/${project.id}/${task.id}`,
    )
  })
})

test.describe("Document library page", () => {
  /* @act
  ## Goals
  When the library has no documents, the page shows an empty state with an "Add Documents"
  intro message and button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /docs/library/{project_id}.
  - Empty state shows text: "Documents add knowledge to your project, which can be searched by tasks (RAG)."
  - Empty state has an "Add Documents" button.

  ## Assertions
  - The "Add Documents" button is visible.
  - The empty-state description text is visible.
  - No table is present.
  */
  test("shows empty state when no documents exist", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/library/${project.id}`)

    await expect(
      page.getByText(
        "Documents add knowledge to your project, which can be searched by tasks",
      ),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Add Documents" }),
    ).toBeVisible()

    await expect(page.locator("table")).not.toBeVisible()
  })

  /* @act
  ## Goals
  When a document has been uploaded, the library page shows a table with the document name,
  type, size, and creation date.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a document via bulk upload)

  ## Hints
  - Seed a text file via POST /api/projects/{project_id}/documents/bulk multipart.
  - Table columns: Type, Name, Size, Created At.
  - The document friendly_name appears in the Name column.

  ## Assertions
  - A table is visible on the page.
  - The seeded document's friendly name appears in the table.
  - Column headers Type, Name, Size, Created At are present.
  */
  test("shows uploaded document in table", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await seedDocument(
      apiRequest,
      project.id,
      "test-doc.txt",
      "Hello world test content",
    )

    await page.goto(`/docs/library/${project.id}`)

    const table = page.locator("table")
    await expect(table).toBeVisible()

    await expect(table.getByText("test-doc.txt")).toBeVisible()

    for (const header of ["Type", "Name", "Size", "Created At"]) {
      await expect(
        table.locator("th").filter({ hasText: header }),
      ).toBeVisible()
    }
  })

  /* @act
  ## Goals
  Clicking the Select button enters selection mode. In selection mode, clicking a document
  row toggles its checkbox. The selected count label updates accordingly.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a document)

  ## Hints
  - "Select" button enters selection mode.
  - "Cancel Selection" button exits selection mode.
  - Selected count shows "{n} selected" text.

  ## Assertions
  - After clicking Select, the "Cancel Selection" button appears.
  - Clicking a document row checks its checkbox and shows "1 selected".
  - Clicking "Cancel Selection" returns to normal mode.
  */
  test("select mode toggles document selection", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await seedDocument(
      apiRequest,
      project.id,
      "selectable-doc.txt",
      "Content for selection test",
    )

    await page.goto(`/docs/library/${project.id}`)
    await expect(page.locator("table")).toBeVisible()

    await page.getByRole("button", { name: "Select", exact: true }).click()

    await expect(
      page.getByRole("button", { name: "Cancel Selection" }),
    ).toBeVisible()

    await expect(page.getByText("0 selected")).toBeVisible()

    // Click on the document row to select it
    await page.locator("table tbody tr").first().click()

    await expect(page.getByText("1 selected")).toBeVisible()

    // Exit selection mode
    await page.getByRole("button", { name: "Cancel Selection" }).click()

    await expect(
      page.getByRole("button", { name: "Select", exact: true }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Clicking a document row in normal mode (not select mode) navigates to the document
  detail page.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a document)

  ## Hints
  - In normal mode, clicking a row calls goto(/docs/library/{project_id}/{document_id}).

  ## Assertions
  - After clicking the document row, the URL matches /docs/library/{project_id}/{document_id}.
  */
  test("clicking document row navigates to detail page", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const doc = await seedDocument(
      apiRequest,
      project.id,
      "nav-test-doc.txt",
      "Content for navigation test",
    )

    await page.goto(`/docs/library/${project.id}`)
    await expect(page.locator("table")).toBeVisible()

    await page.locator("table tbody tr").first().click()

    await expect(page).toHaveURL(`/docs/library/${project.id}/${doc.id}`)
  })

  /* @act
  ## Goals
  Column headers in the document table are clickable for sorting. Clicking a column header
  toggles a sort indicator arrow.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a document)

  ## Hints
  - Clicking a column header calls handleSort(key).
  - Active sort column shows a triangle indicator.

  ## Assertions
  - The default sort column "Created At" shows a down arrow indicator.
  - Clicking the "Name" header changes the sort indicator to that column.
  */
  test("table column headers support sorting", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await seedDocument(
      apiRequest,
      project.id,
      "sort-test-doc.txt",
      "Content for sort test",
    )

    await page.goto(`/docs/library/${project.id}`)
    await expect(page.locator("table")).toBeVisible()

    // Default sort is "Created At" descending
    const createdAtHeader = page
      .locator("table th")
      .filter({ hasText: "Created At" })
    await expect(createdAtHeader).toContainText("▼")

    // Click Name header to sort by name
    const nameHeader = page.locator("table th").filter({ hasText: "Name" })
    await nameHeader.click()

    // Name header should now have a sort indicator
    await expect(nameHeader).toContainText("▼")
  })

  /* @act
  ## Goals
  The document library page shows breadcrumbs including "Docs & Search" linking back
  to the docs overview page.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Breadcrumbs include "Optimize" and "Docs & Search".
  - "Docs & Search" links to /docs/{project_id}.

  ## Assertions
  - A "Docs & Search" breadcrumb link is visible pointing to /docs/{project_id}.
  */
  test("shows Docs and Search breadcrumb", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/library/${project.id}`)
    await page.waitForLoadState("networkidle")

    const breadcrumb = page
      .locator(".breadcrumbs")
      .getByRole("link", { name: "Docs & Search", exact: true })
    await expect(breadcrumb).toHaveAttribute("href", `/docs/${project.id}`)
  })
})

test.describe("Document detail page", () => {
  /* @act
  ## Goals
  The document detail page loads and shows the document properties panel with
  ID, Name, File Size, Kind, MIME Type, Created At, Created By, and Description.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a document)

  ## Hints
  - Route is /docs/library/{project_id}/{document_id}.
  - Properties are shown in a PropertyList component with label-value pairs.
  - The page title is "Document" with the document name as subtitle.

  ## Assertions
  - The heading "Document" is visible.
  - The document friendly_name is shown as the subtitle.
  - Property labels ID, Name, File Size, Kind, MIME Type, Created At are visible.
  */
  test("shows document properties", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const doc = await seedDocument(
      apiRequest,
      project.id,
      "props-test-doc.txt",
      "Content for properties test",
    )

    await page.goto(`/docs/library/${project.id}/${doc.id}`)

    await expect(
      page.getByRole("heading", { name: "Document", exact: true }),
    ).toBeVisible()

    // Document subtitle shows the friendly name
    await expect(page.getByText("props-test-doc.txt").first()).toBeVisible()

    // Properties panel has expected labels
    for (const label of [
      "ID",
      "Name",
      "File Size",
      "Kind",
      "MIME Type",
      "Created At",
    ]) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
    }
  })

  /* @act
  ## Goals
  The document detail page shows an extractions section. When no extractions exist,
  it displays "No extractions found for this document."

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a document)

  ## Hints
  - The section heading is "Document Extractions".
  - Empty state message: "No extractions found for this document."

  ## Assertions
  - "Document Extractions" heading is visible.
  - "No extractions found for this document." message is visible.
  */
  test("shows empty extractions section", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const doc = await seedDocument(
      apiRequest,
      project.id,
      "extraction-test-doc.txt",
      "Content for extraction test",
    )

    await page.goto(`/docs/library/${project.id}/${doc.id}`)

    await expect(page.getByText("Document Extractions")).toBeVisible()
    await expect(
      page.getByText("No extractions found for this document."),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The document detail page has breadcrumbs linking back to Optimize, Docs & Search,
  and Document Library.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a document)

  ## Hints
  - Breadcrumbs: Optimize, Docs & Search, Document Library.

  ## Assertions
  - "Document Library" breadcrumb links to /docs/library/{project_id}.
  - "Docs & Search" breadcrumb links to /docs/{project_id}.
  */
  test("shows breadcrumbs with correct links", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const doc = await seedDocument(
      apiRequest,
      project.id,
      "breadcrumb-test-doc.txt",
      "Content for breadcrumb test",
    )

    await page.goto(`/docs/library/${project.id}/${doc.id}`)

    const breadcrumbs = page.locator(".breadcrumbs")

    await expect(
      breadcrumbs.getByRole("link", { name: "Document Library" }),
    ).toHaveAttribute("href", `/docs/library/${project.id}`)

    await expect(
      breadcrumbs.getByRole("link", { name: "Docs & Search" }),
    ).toHaveAttribute("href", `/docs/${project.id}`)
  })

  /* @act
  ## Goals
  Clicking the delete icon on the document detail page opens a confirmation dialog.
  Confirming deletion removes the document and navigates back to the library.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a document)

  ## Hints
  - The delete button is an icon button with img src ending in /images/delete.svg.
  - The confirmation dialog has a "Delete" button.
  - After deletion, user is redirected to /docs/library/{project_id}.

  ## Assertions
  - A delete confirmation dialog appears after clicking the delete icon.
  - After confirming, the URL is /docs/library/{project_id}.
  - The deleted document no longer appears in the library (GET returns 404).
  */
  test("delete button removes document and redirects to library", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const doc = await seedDocument(
      apiRequest,
      project.id,
      "delete-test-doc.txt",
      "Content for delete test",
    )

    await page.goto(`/docs/library/${project.id}/${doc.id}`)

    await expect(page.getByText("delete-test-doc.txt").first()).toBeVisible()

    // Click the delete icon button
    await page.locator('button:has(img[src$="/images/delete.svg"])').click()

    // Confirmation dialog appears
    const dialog = page
      .getByRole("dialog")
      .filter({ hasText: /Delete delete-test-doc/ })
    await expect(dialog).toBeVisible()
    await dialog.getByRole("button", { name: "Delete", exact: true }).click()

    // Redirected to library
    await expect(page).toHaveURL(`/docs/library/${project.id}`)

    // Document no longer accessible
    await expect
      .poll(async () => {
        const resp = await apiRequest.get(
          `/api/projects/${encodeURIComponent(project.id)}/documents/${encodeURIComponent(doc.id)}`,
        )
        return resp.status()
      })
      .toBe(404)
  })

  /* @act
  ## Goals
  Clicking the Edit button on the document detail page opens an edit dialog with
  name and description fields.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a document)

  ## Hints
  - The "Edit" button is in the page header action buttons.
  - The edit dialog has fields for Name and Description.

  ## Assertions
  - An edit dialog appears with a Name input and a Description textarea.
  - The Name field is pre-populated with the document name.
  */
  test("edit button opens edit dialog with document fields", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const doc = await seedDocument(
      apiRequest,
      project.id,
      "edit-test-doc.txt",
      "Content for edit test",
    )

    await page.goto(`/docs/library/${project.id}/${doc.id}`)

    await expect(page.getByText("edit-test-doc.txt").first()).toBeVisible()

    await page.getByRole("button", { name: "Edit", exact: true }).click()

    const dialog = page.getByRole("dialog").filter({ hasText: "Edit Document" })
    await expect(dialog).toBeVisible()

    // The dialog should have Name and Description labels
    await expect(
      dialog.getByText("Name", { exact: true }).first(),
    ).toBeVisible()
    await expect(
      dialog.getByText("Description", { exact: true }).first(),
    ).toBeVisible()
  })
})
