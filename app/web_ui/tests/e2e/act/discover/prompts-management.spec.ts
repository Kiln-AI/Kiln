import { test, expect } from "../../fixtures"

test.describe("Prompts management", () => {
  /* @act
  ## Goals
  The prompts list page loads and displays the page title, subtitle, action buttons,
  and empty state message when no prompts exist.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /prompts/{project_id}/{task_id}
  - Page title is "Prompts" with subtitle "Manage prompts for this task."
  - Action buttons: "Optimizer Jobs" and "Create Prompt"
  - Empty state shows "No saved prompts yet."
  - "Read the Docs" link points to https://docs.kiln.tech/docs/prompts

  ## Assertions
  - Page heading "Prompts" is visible.
  - "Manage prompts for this task." text is visible.
  - "Optimizer Jobs" link is visible.
  - "Create Prompt" link is visible.
  - "No saved prompts yet." text is visible.
  - "Read the Docs" link has correct href.
  */
  test("prompts list page loads with empty state", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/prompts/${project.id}/${task.id}`)

    await expect(
      page.getByRole("heading", { name: "Prompts", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Manage prompts for this task.")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Optimizer Jobs" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Create Prompt" }),
    ).toBeVisible()

    await expect(page.getByText("No saved prompts yet.")).toBeVisible()

    const readDocsLink = page.getByRole("link", { name: "Read the Docs" })
    await expect(readDocsLink).toBeVisible()
    await expect(readDocsLink).toHaveAttribute(
      "href",
      "https://docs.kiln.tech/docs/prompts",
    )
  })

  /* @act
  ## Goals
  The prompts list page shows the base task prompt section with the seeded task
  instruction text and a "View & Edit" button linking to the edit page.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /prompts/{project_id}/{task_id}
  - The "Base Task Prompt" section shows the task instruction
  - "View & Edit" button links to /prompts/{project_id}/{task_id}/edit_base_prompt
  - The seeded task instruction is "ActRight fixture task instruction."

  ## Assertions
  - "Base Task Prompt" text is visible.
  - The seeded task instruction text is visible in the base prompt section.
  - "View & Edit" button is visible.
  */
  test("prompts list shows base task prompt section", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/prompts/${project.id}/${task.id}`)

    await expect(
      page.getByRole("heading", { name: "Prompts", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Base Task Prompt")).toBeVisible()

    await expect(
      page.getByText("ActRight fixture task instruction."),
    ).toBeVisible()

    await expect(page.getByText("View & Edit")).toBeVisible()
  })

  /* @act
  ## Goals
  The prompts list page shows the optimizer banner with a call to action to
  automatically optimize the prompt.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /prompts/{project_id}/{task_id}
  - The Banner component shows "Automatically Optimize Your Prompt" title
  - The banner has a "Create Optimized Prompt" button/link

  ## Assertions
  - "Automatically Optimize Your Prompt" text is visible.
  - "Create Optimized Prompt" link is visible.
  */
  test("prompts list shows optimize banner", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/prompts/${project.id}/${task.id}`)

    await expect(
      page.getByRole("heading", { name: "Prompts", exact: true }),
    ).toBeVisible()

    await expect(
      page.getByText("Automatically Optimize Your Prompt"),
    ).toBeVisible()

    await expect(
      page.getByRole("link", { name: "Create Optimized Prompt" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The create prompt page loads in custom mode (no generator_id) and shows a form
  with prompt name, prompt textarea, and chain of thought toggle.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /prompts/{project_id}/{task_id}/create (no query params for custom mode)
  - Page title is "Create Prompt" with subtitle "Custom"
  - Form fields: #prompt_name, #prompt, #is_chain_of_thought
  - The prompt textarea is pre-populated with the task instruction in custom mode
  - Submit button label is "Create Prompt"

  ## Assertions
  - Page heading "Create Prompt" is visible.
  - "Custom" subtitle text is visible.
  - Prompt name input is visible.
  - Prompt textarea is visible.
  - Chain of thought select is visible.
  - "Create Prompt" button is visible.
  */
  test("create prompt page loads in custom mode", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/prompts/${project.id}/${task.id}/create`)

    await expect(
      page.getByRole("heading", { name: "Create Prompt", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Custom")).toBeVisible()

    await expect(page.locator("#prompt_name")).toBeVisible()

    await expect(page.locator("#prompt")).toBeVisible()

    await expect(page.locator("#is_chain_of_thought")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Create Prompt" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The edit base prompt page loads and pre-populates the form with the seeded
  task's instruction text.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /prompts/{project_id}/{task_id}/edit_base_prompt
  - Page title is "Edit Task Prompt"
  - Form fields: #task_instruction (textarea), #thinking_instructions (textarea)
  - The task instruction textarea is pre-populated with the seeded task instruction
  - Save button label is "Save"

  ## Assertions
  - Page heading "Edit Task Prompt" is visible.
  - The task instruction textarea has the seeded task instruction as its value.
  - The thinking instructions textarea is visible.
  - "Save" button is visible.
  */
  test("edit base prompt page loads with task instruction", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/prompts/${project.id}/${task.id}/edit_base_prompt`)

    await expect(
      page.getByRole("heading", { name: "Edit Task Prompt" }),
    ).toBeVisible()

    await expect(page.locator("#task_instruction")).toHaveValue(
      task.instruction,
    )

    await expect(page.locator("#thinking_instructions")).toBeVisible()

    await expect(page.getByRole("button", { name: "Save" })).toBeVisible()
  })

  /* @act
  ## Goals
  Editing the base prompt instruction and saving updates the task via PATCH.
  After save, the API returns the new instruction value.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /prompts/{project_id}/{task_id}/edit_base_prompt
  - Fill #task_instruction with new text, click "Save"
  - After save, page navigates back to /prompts/{project_id}/{task_id}
  - Verify via API GET that the instruction was updated

  ## Assertions
  - After save, GET /api/projects/:pid/tasks/:tid returns the new instruction.
  */
  test("edit base prompt page saves changes", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/prompts/${project.id}/${task.id}/edit_base_prompt`)

    await expect(page.locator("#task_instruction")).toHaveValue(
      task.instruction,
    )

    const newInstruction = "Updated base prompt instruction for testing."
    await page.locator("#task_instruction").fill(newInstruction)

    await page.getByRole("button", { name: "Save" }).click()

    await page.waitForURL(`**/prompts/${project.id}/${task.id}`)

    await expect
      .poll(async () => {
        const resp = await apiRequest.get(
          `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}`,
        )
        if (!resp.ok()) return null
        const data = (await resp.json()) as { instruction?: string }
        return data.instruction
      })
      .toBe(newInstruction)
  })

  /* @act
  ## Goals
  The prompt generators page loads and shows all three generator categories:
  Automatic Optimization, Prompt Generators, and Manual.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /prompts/{project_id}/{task_id}/prompt_generators
  - Page title is "Create Prompt"
  - Categories rendered via CarouselSection: "Automatic Optimization",
    "Prompt Generators", "Manual"
  - Items include "Kiln Optimized", "Few-Shot", "Many-Shot", "Custom", etc.
  - "Kiln Optimized" is recommended

  ## Assertions
  - Page heading "Create Prompt" is visible.
  - "Automatic Optimization" heading is visible.
  - "Prompt Generators" heading is visible.
  - "Manual" heading is visible.
  - "Kiln Optimized" text is visible.
  - "Custom" text is visible.
  */
  test("prompt generators page shows generator categories", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/prompts/${project.id}/${task.id}/prompt_generators`)

    await expect(
      page.getByRole("heading", { name: "Create Prompt", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Automatic Optimization")).toBeVisible()

    await expect(
      page.getByText("Prompt Generators", { exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Manual", { exact: true })).toBeVisible()

    await expect(page.getByText("Kiln Optimized")).toBeVisible()

    await expect(page.getByText("Custom")).toBeVisible()
  })

  /* @act
  ## Goals
  On the prompt generators page, clicking a generator that requires rated data
  (like "Few-Shot") shows an "Option Unavailable" dialog with a reason about
  needing rated examples when no data exists.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /prompts/{project_id}/{task_id}/prompt_generators
  - Generators like "Few-Shot" require rated data
  - Clicking a disabled generator shows a Dialog titled "Option Unavailable"
  - The dialog contains text about "rated examples from your dataset"
  - "Chain of Thought" does not require data and should be clickable

  ## Assertions
  - "Few-Shot" text is visible on the page.
  - Clicking "Few-Shot" opens an "Option Unavailable" dialog.
  - The dialog contains text about rated examples.
  - "Chain of Thought" text is visible (it should not be disabled).
  */
  test("prompt generators page shows disabled generators without data", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/prompts/${project.id}/${task.id}/prompt_generators`)

    await expect(
      page.getByRole("heading", { name: "Create Prompt", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Few-Shot", { exact: true })).toBeVisible()

    await page.getByText("Few-Shot", { exact: true }).click()

    await expect(
      page.getByRole("heading", { name: "Option Unavailable" }).first(),
    ).toBeVisible()

    await expect(
      page.getByText("rated examples from your dataset").first(),
    ).toBeVisible()

    await expect(
      page.getByText("Chain of Thought", { exact: true }).first(),
    ).toBeVisible()
  })
})
