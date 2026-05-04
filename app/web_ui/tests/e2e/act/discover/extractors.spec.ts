import { test, expect } from "../../fixtures"

test.describe("Extractors list page", () => {
  /* @act
  ## Goals
  When no extractors exist for a project, the extractors list page shows an empty state
  with an intro message about extractors and a Create Extractor button linking to the
  create extractor page.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /docs/extractors/{project_id}
  - Page title is "Document Extractors"
  - Empty state shows "Add Extractors to Your Project" intro
  - Empty state has a "Create Extractor" button linking to /docs/extractors/{project_id}/create_extractor
  - Breadcrumbs include "Docs & Search"

  ## Assertions
  - Page heading "Document Extractors" is visible.
  - Empty state text "Extractors convert files like PDFs or images into text" is visible.
  - "Create Extractor" button is visible and links to create extractor page.
  - "Docs & Search" breadcrumb is visible.
  */
  test("shows empty state with create button when no extractors exist", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/extractors/${project.id}`)

    await expect(
      page.getByRole("heading", { name: "Document Extractors" }),
    ).toBeVisible()

    await expect(
      page.getByText(
        "Extractors convert files like PDFs or images into text your models can use.",
      ),
    ).toBeVisible()

    const createBtn = page.getByRole("link", { name: "Create Extractor" })
    await expect(createBtn).toBeVisible()
    await expect(createBtn).toHaveAttribute(
      "href",
      `/docs/extractors/${project.id}/create_extractor`,
    )

    const breadcrumb = page
      .locator(".breadcrumbs")
      .getByRole("link", { name: "Docs & Search" })
    await expect(breadcrumb).toHaveAttribute("href", `/docs/${project.id}`)
  })
})

test.describe("Create extractor page", () => {
  /* @act
  ## Goals
  The create extractor page renders the form with an Extraction Model dropdown,
  an Output Format selector with Markdown (recommended) and Plain Text options,
  and a Create Extractor submit button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /docs/extractors/{project_id}/create_extractor
  - Page title is "Create Document Extractor"
  - Form has Extraction Model label and Output Format label
  - Output Format has "Markdown" with "Recommended" badge and "Plain Text" option
  - Submit button label is "Create Extractor"
  - Breadcrumbs include "Extractors" linking to /docs/extractors/{project_id}

  ## Assertions
  - Page heading "Create Document Extractor" is visible.
  - "Extraction Model" label text is visible.
  - "Output Format" label text is visible.
  - "Markdown" option is visible.
  - "Create Extractor" submit button is visible.
  - "Extractors" breadcrumb links to /docs/extractors/{project_id}.
  */
  test("renders form with model dropdown and format selector", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/extractors/${project.id}/create_extractor`)

    await expect(
      page.getByRole("heading", { name: "Create Document Extractor" }),
    ).toBeVisible()

    await expect(
      page.getByText("Extraction Model", { exact: true }),
    ).toBeVisible()
    await expect(page.getByText("Output Format")).toBeVisible()
    await expect(page.getByText("Markdown", { exact: true })).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Create Extractor" }),
    ).toBeVisible()

    const breadcrumb = page
      .locator(".breadcrumbs")
      .getByRole("link", { name: "Extractors" })
    await expect(breadcrumb).toHaveAttribute(
      "href",
      `/docs/extractors/${project.id}`,
    )
  })

  /* @act
  ## Goals
  The create extractor form has an Advanced Options collapse section. Expanding it
  reveals prompt fields for Document, Image, Video, and Audio extraction, plus
  name and description fields.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - "Advanced Options" is a collapsible section
  - Contains prompt textareas: Document Extraction Prompt, Image Extraction Prompt, Video Extraction Prompt, Audio Extraction Prompt
  - Contains Extractor Name input and Description textarea
  - Prompt fields have pre-filled default values

  ## Assertions
  - "Advanced Options" toggle is visible.
  - After expanding, "Document Extraction Prompt" label is visible.
  - "Image Extraction Prompt" label is visible.
  - "Extractor Name" label is visible.
  - "Description" label is visible.
  */
  test("advanced options section shows prompt and detail fields", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/extractors/${project.id}/create_extractor`)

    await expect(
      page.getByRole("heading", { name: "Create Document Extractor" }),
    ).toBeVisible()

    const advancedToggle = page.getByText("Advanced Options")
    await expect(advancedToggle).toBeVisible()
    await advancedToggle
      .locator("xpath=ancestor::div[contains(@class,'collapse')]")
      .locator("input[type='checkbox']")
      .check({ force: true })

    await expect(page.getByText("Document Extraction Prompt")).toBeVisible()
    await expect(page.getByText("Image Extraction Prompt")).toBeVisible()
    await expect(page.getByText("Video Extraction Prompt")).toBeVisible()
    await expect(page.getByText("Audio Extraction Prompt")).toBeVisible()
    await expect(page.getByText("Extractor Name")).toBeVisible()
  })
})

test.describe("Extractor detail page", () => {
  /* @act
  ## Goals
  After creating an extractor via the API, navigating to the extractor detail page
  shows the extractor properties (ID, Name, Type, Model Provider, Model, Output Format,
  Created At) and extraction prompt sections (Document, Image, Video, Audio).

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed an extractor via POST)

  ## Hints
  - Route is /docs/extractors/{project_id}/{extractor_id}/extractor
  - Page title is "Document Extractor" with subtitle showing the extractor name
  - Properties are shown in a PropertyList: ID, Name, Type, Model Provider, Model, Output Format, Created At, Created By, Description
  - Extraction prompts section has heading "Extraction Prompts"
  - Prompt subsections: Document Prompt, Image Prompt, Video Prompt, Audio Prompt
  - Archive button is present in header

  ## Assertions
  - Page heading "Document Extractor" is visible.
  - "Extraction Prompts" heading is visible.
  - Property labels ID, Name, Type, Model are visible.
  - Archive button is visible.
  - "Extractors" breadcrumb links to /docs/extractors/{project_id}.
  */
  test("shows extractor properties and prompts after creation", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const resp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/create_extractor_config`,
      {
        data: {
          name: "Test Extractor",
          description: "A test extractor",
          model_provider_name: "openai",
          model_name: "gpt_4o",
          output_format: "text/markdown",
          properties: {
            extractor_type: "litellm",
            prompt_document: "Transcribe the document.",
            prompt_image: "Describe the image.",
            prompt_video: "Describe the video.",
            prompt_audio: "Transcribe the audio.",
          },
          passthrough_mimetypes: ["text/plain", "text/markdown"],
        },
      },
    )
    expect(resp.ok(), "seed extractor").toBeTruthy()
    const extractor = await resp.json()

    await page.goto(`/docs/extractors/${project.id}/${extractor.id}/extractor`)

    await expect(
      page.getByRole("heading", { name: "Document Extractor" }),
    ).toBeVisible()

    await expect(page.getByText("Extraction Prompts")).toBeVisible()

    await expect(page.getByText("Document Prompt")).toBeVisible()
    await expect(page.getByText("Image Prompt")).toBeVisible()
    await expect(page.getByText("Video Prompt")).toBeVisible()
    await expect(page.getByText("Audio Prompt")).toBeVisible()

    for (const label of ["ID", "Name", "Type", "Model"]) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
    }

    await expect(page.getByRole("button", { name: "Archive" })).toBeVisible()

    const breadcrumb = page
      .locator(".breadcrumbs")
      .getByRole("link", { name: "Extractors" })
    await expect(breadcrumb).toHaveAttribute(
      "href",
      `/docs/extractors/${project.id}`,
    )
  })
})

test.describe("Add search tool page", () => {
  /* @act
  ## Goals
  The add search tool page shows suggested RAG configurations in a carousel and a
  custom configuration section. The page title is "Add a Search Tool (RAG)".
  Suggested configs include Best Quality, Cost Optimized, All Local, and Vector Only.
  The custom section has a "Create Custom" button with "Advanced" badge.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /docs/rag_configs/{project_id}/add_search_tool
  - Page title is "Add a Search Tool (RAG)"
  - Section heading "Suggested Configurations"
  - FeatureCarousel shows templates: Best Quality, Cost Optimized, All Local, Vector Only
  - Custom section has "Custom Search Tool" with "Advanced" badge and "Create Custom" button
  - Breadcrumbs include "Search Tools" linking to /docs/rag_configs/{project_id}

  ## Assertions
  - Page heading "Add a Search Tool (RAG)" is visible.
  - "Suggested Configurations" heading is visible.
  - Template names "Best Quality", "Cost Optimized", "All Local", "Vector Only" are visible.
  - "Custom Search Tool" text is visible.
  - "Create Custom" button is visible.
  - "Search Tools" breadcrumb links to /docs/rag_configs/{project_id}.
  */
  test("shows suggested configs and custom option", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/docs/rag_configs/${project.id}/add_search_tool`)

    await expect(
      page.getByRole("heading", { name: "Add a Search Tool (RAG)" }),
    ).toBeVisible()

    await expect(
      page.getByRole("heading", { name: "Suggested Configurations" }),
    ).toBeVisible()

    await expect(page.getByText("Best Quality").first()).toBeVisible()
    await expect(page.getByText("Cost Optimized").first()).toBeVisible()
    await expect(page.getByText("All Local").first()).toBeVisible()
    await expect(page.getByText("Vector Only").first()).toBeVisible()

    await expect(
      page.getByRole("heading", { name: "Custom Search Tool" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Create Custom" }),
    ).toBeVisible()

    const breadcrumb = page
      .locator(".breadcrumbs")
      .getByRole("link", { name: "Search Tools" })
    await expect(breadcrumb).toHaveAttribute(
      "href",
      `/docs/rag_configs/${project.id}`,
    )
  })
})
