import { test, expect } from "../../fixtures"

test.describe("Fine-tuning", () => {
  /* @act
  ## Goals
  The fine-tune list page loads in empty state and shows the empty finetune
  component with a "Create a Fine-Tune" button and a "Fine Tuning Guide" link.
  The page title is "Fine Tunes".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /fine_tune/{project_id}/{task_id}
  - When no finetunes exist, the page shows EmptyFinetune component
  - EmptyFinetune has heading text about fine-tuning learning from dataset
  - "Create a Fine-Tune" is a link styled as a button
  - "Fine Tuning Guide" is an external link

  ## Assertions
  - Page heading "Fine Tunes" is visible.
  - Text "Fine-Tuning Learns from Your Dataset to Create Custom Models" is visible.
  - "Create a Fine-Tune" link is visible and has correct href.
  - "Fine Tuning Guide" link is visible and has correct href.
  */
  test("fine-tune list empty state shows create and guide links", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/fine_tune/${project.id}/${task.id}`)

    await expect(
      page.getByRole("heading", { name: "Fine Tunes", exact: true }),
    ).toBeVisible()

    await expect(
      page.getByText(
        "Fine-Tuning Learns from Your Dataset to Create Custom Models",
      ),
    ).toBeVisible()

    const createLink = page.getByRole("link", {
      name: "Create a Fine-Tune",
    })
    await expect(createLink).toBeVisible()
    await expect(createLink).toHaveAttribute(
      "href",
      `/fine_tune/${project.id}/${task.id}/create_finetune`,
    )

    const guideLink = page.getByRole("link", {
      name: "Fine Tuning Guide",
    })
    await expect(guideLink).toBeVisible()
    await expect(guideLink).toHaveAttribute(
      "href",
      "https://docs.kiln.tech/docs/fine-tuning-guide",
    )
  })

  /* @act
  ## Goals
  The fine-tune list page has a "Read the Docs" sub-subtitle link pointing
  to the fine-tuning guide and an Optimize breadcrumb.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /fine_tune/{project_id}/{task_id}
  - "Read the Docs" is a sub-subtitle link
  - Breadcrumbs contain "Optimize" which links to /optimize/{project_id}/{task_id}

  ## Assertions
  - "Read the Docs" link has the correct href.
  - "Optimize" breadcrumb link is visible.
  */
  test("fine-tune list page has docs link and optimize breadcrumb", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/fine_tune/${project.id}/${task.id}`)

    await expect(
      page.getByRole("heading", { name: "Fine Tunes", exact: true }),
    ).toBeVisible()

    const readDocsLink = page.getByRole("link", { name: "Read the Docs" })
    await expect(readDocsLink).toBeVisible()
    await expect(readDocsLink).toHaveAttribute(
      "href",
      "https://docs.kiln.tech/docs/fine-tuning-guide",
    )

    const optimizeBreadcrumb = page
      .locator(".breadcrumbs")
      .getByRole("link", { name: "Optimize" })
    await expect(optimizeBreadcrumb).toBeVisible()
    await expect(optimizeBreadcrumb).toHaveAttribute(
      "href",
      `/optimize/${project.id}/${task.id}`,
    )
  })

  /* @act
  ## Goals
  The create fine-tune page loads and shows Step 1 with the model/provider
  selector, Step 2 with prompt type configuration, and action buttons.
  The page title is "Create a New Fine Tune".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /fine_tune/{project_id}/{task_id}/create_finetune
  - Page shows "Step 1: Select Base Model to Fine-Tune"
  - Page shows "Step 2: Configure Fine-Tuning Run Configuration"
  - Has "Reset" and "Docs & Guide" action buttons
  - Has a "Fine Tunes" breadcrumb

  ## Assertions
  - Page heading "Create a New Fine Tune" is visible.
  - "Step 1: Select Base Model to Fine-Tune" text is visible.
  - "Step 2: Configure Fine-Tuning Run Configuration" text is visible.
  - "Reset" button is visible.
  - "Docs & Guide" link is visible.
  - "Fine Tunes" breadcrumb link is visible.
  */
  test("create fine-tune page shows steps and action buttons", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/fine_tune/${project.id}/${task.id}/create_finetune`)

    await expect(
      page.getByRole("heading", { name: "Create a New Fine Tune" }),
    ).toBeVisible()

    await expect(
      page.getByText("Step 1: Select Base Model to Fine-Tune"),
    ).toBeVisible()

    await expect(
      page.getByText("Step 2: Configure Fine-Tuning Run Configuration"),
    ).toBeVisible()

    await expect(page.getByRole("button", { name: "Reset" })).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Docs & Guide" }),
    ).toBeVisible()

    const breadcrumb = page.getByRole("link", { name: "Fine Tunes" })
    await expect(breadcrumb).toBeVisible()
    await expect(breadcrumb).toHaveAttribute(
      "href",
      `/fine_tune/${project.id}/${task.id}`,
    )
  })

  /* @act
  ## Goals
  The create fine-tune page shows the "Model & Provider" form field with
  a description mentioning downloading a JSONL file option.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /fine_tune/{project_id}/{task_id}/create_finetune
  - The Model & Provider field has description text about downloading JSONL
  - The label is "Model & Provider"
  - The select has option groups including "Download Dataset"

  ## Assertions
  - "Model & Provider" label text is visible.
  - Description mentioning "download a JSONL file" is visible.
  */
  test("create fine-tune page shows model and provider selector", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/fine_tune/${project.id}/${task.id}/create_finetune`)

    await expect(
      page.getByRole("heading", { name: "Create a New Fine Tune" }),
    ).toBeVisible()

    await expect(page.getByText("Model & Provider")).toBeVisible()

    await expect(
      page.getByText("download a JSONL file to fine-tune using any"),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The create fine-tune page shows the Reasoning (data strategy) selector
  and the prompt type selector under Step 2.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /fine_tune/{project_id}/{task_id}/create_finetune
  - "Reasoning" label is visible for the data strategy field
  - The prompt type selector is visible with "System prompt" or prompt method options

  ## Assertions
  - "Reasoning" label text is visible.
  - Description "Should the model be trained on reasoning/thinking content?" is visible.
  */
  test("create fine-tune page shows reasoning selector", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/fine_tune/${project.id}/${task.id}/create_finetune`)

    await expect(
      page.getByRole("heading", { name: "Create a New Fine Tune" }),
    ).toBeVisible()

    await expect(page.getByText("Reasoning", { exact: true })).toBeVisible()

    await expect(
      page.getByText(
        "Should the model be trained on reasoning/thinking content?",
      ),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The create fine-tune page has a provider connection warning with a link
  to connect providers for 1-click fine-tuning.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /fine_tune/{project_id}/{task_id}/create_finetune
  - Warning message mentions "For 1-click fine-tuning connect OpenAI, Fireworks, Together, or Google Vertex."
  - The warning is a clickable button that navigates to provider settings

  ## Assertions
  - Warning text about connecting providers is visible.
  */
  test("create fine-tune page shows provider connection warning", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/fine_tune/${project.id}/${task.id}/create_finetune`)

    await expect(
      page.getByRole("heading", { name: "Create a New Fine Tune" }),
    ).toBeVisible()

    await expect(
      page.getByText(
        "For 1-click fine-tuning connect OpenAI, Fireworks, Together, or Google Vertex.",
      ),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The create fine-tune page Read the Docs sub-subtitle link points to the
  fine-tuning guide documentation.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /fine_tune/{project_id}/{task_id}/create_finetune
  - "Read the Docs" is a sub-subtitle link with the correct href

  ## Assertions
  - "Read the Docs" link is visible.
  - "Read the Docs" link has the correct href to fine-tuning guide.
  */
  test("create fine-tune page docs link has correct href", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/fine_tune/${project.id}/${task.id}/create_finetune`)

    await expect(
      page.getByRole("heading", { name: "Create a New Fine Tune" }),
    ).toBeVisible()

    const readDocsLink = page.getByRole("link", { name: "Read the Docs" })
    await expect(readDocsLink).toBeVisible()
    await expect(readDocsLink).toHaveAttribute(
      "href",
      "https://docs.kiln.tech/docs/fine-tuning-guide",
    )
  })
})
