import { test, expect } from "../../fixtures"

test.describe("Prompt detail views", () => {
  /* @act
  ## Goals
  The saved prompt detail page loads and displays the prompt content, name,
  and metadata properties (ID, Name, Type, Created By, Created At) for a
  custom prompt created via the API.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to create a prompt via POST)

  ## Hints
  - Create a prompt via POST /api/projects/{pid}/tasks/{tid}/prompts
  - Navigate to /prompts/{pid}/{tid}/saved/id::{prompt.id}
  - Page title is "Saved Prompt" with subtitle being the prompt name
  - Prompt content is shown under a "Prompt" heading
  - Details sidebar shows ID, Name, Type (Custom for id:: prompts), Created By, Created At

  ## Assertions
  - Page heading "Saved Prompt" is visible.
  - Prompt name appears as subtitle.
  - Prompt content text is visible.
  - "Prompt" section heading is visible.
  - "Details" section heading is visible.
  - The metadata grid shows the prompt Name and Type "Custom".
  */
  test("saved prompt page shows prompt details", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    const createResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/prompts`,
      {
        data: {
          name: "Test Prompt Alpha",
          prompt: "You are a helpful assistant for testing.",
          chain_of_thought_instructions: null,
        },
      },
    )
    expect(createResp.ok(), "POST create prompt").toBeTruthy()
    const promptData = (await createResp.json()) as { id: string }

    await page.goto(
      `/prompts/${project.id}/${task.id}/saved/${encodeURIComponent(`id::${promptData.id}`)}`,
    )

    await expect(
      page.getByRole("heading", { name: "Saved Prompt", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Test Prompt Alpha").first()).toBeVisible()

    await expect(
      page.getByText("You are a helpful assistant for testing."),
    ).toBeVisible()

    await expect(page.getByText("Prompt", { exact: true })).toBeVisible()

    await expect(page.getByText("Details", { exact: true })).toBeVisible()

    await expect(page.getByText("Custom")).toBeVisible()
  })

  /* @act
  ## Goals
  The saved prompt detail page displays Chain of Thought Instructions section
  when the prompt has chain_of_thought_instructions set.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to create a prompt with CoT instructions)

  ## Hints
  - Create a prompt with chain_of_thought_instructions via the API
  - Navigate to /prompts/{pid}/{tid}/saved/id::{prompt.id}
  - "Chain of Thought Instructions" heading appears when CoT instructions are set
  - The CoT instructions text is displayed below that heading

  ## Assertions
  - "Chain of Thought Instructions" text is visible.
  - The CoT instructions content is visible.
  */
  test("saved prompt page shows chain of thought instructions", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    const createResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/prompts`,
      {
        data: {
          name: "CoT Prompt",
          prompt: "You are a reasoning assistant.",
          chain_of_thought_instructions: "Think step by step before answering.",
        },
      },
    )
    expect(createResp.ok(), "POST create CoT prompt").toBeTruthy()
    const promptData = (await createResp.json()) as { id: string }

    await page.goto(
      `/prompts/${project.id}/${task.id}/saved/${encodeURIComponent(`id::${promptData.id}`)}`,
    )

    await expect(
      page.getByRole("heading", { name: "Saved Prompt", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Chain of Thought Instructions")).toBeVisible()

    await expect(
      page.getByText("Think step by step before answering."),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The saved prompt detail page shows a Clone button that links to the clone page
  for the current prompt.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to create a prompt)

  ## Hints
  - Create a prompt via the API and navigate to its saved page
  - The "Clone" button appears in the action buttons area
  - Clone link points to /prompts/{pid}/{tid}/clone/{encoded_prompt_id}

  ## Assertions
  - "Clone" button/link is visible.
  - Clone link has the correct href containing the prompt ID.
  */
  test("saved prompt page has clone button", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    const createResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/prompts`,
      {
        data: {
          name: "Cloneable Prompt",
          prompt: "A prompt to be cloned.",
          chain_of_thought_instructions: null,
        },
      },
    )
    expect(createResp.ok(), "POST create prompt").toBeTruthy()
    const promptData = (await createResp.json()) as { id: string }
    const promptId = `id::${promptData.id}`

    await page.goto(
      `/prompts/${project.id}/${task.id}/saved/${encodeURIComponent(promptId)}`,
    )

    await expect(
      page.getByRole("heading", { name: "Saved Prompt", exact: true }),
    ).toBeVisible()

    const cloneButton = page.getByRole("button", { name: "Clone" })
    await expect(cloneButton).toBeVisible()
  })

  /* @act
  ## Goals
  The saved prompt detail page shows an Edit button for custom prompts (id:: prefix).
  Clicking Edit opens a dialog with name and description fields. Editing the name
  and saving updates the prompt.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to create and verify prompt)

  ## Hints
  - Create a prompt via the API (custom prompts have id:: prefix)
  - Navigate to the saved prompt page
  - Click "Edit" button to open EditDialog
  - Dialog title is "Edit Prompt"
  - Dialog has fields: "Prompt Name" (input), "Prompt Description" (textarea)
  - Dialog shows warning about locked prompt body
  - Click "Save" in the dialog
  - Verify the name update via API

  ## Assertions
  - "Edit" button is visible on the saved prompt page.
  - Clicking "Edit" opens a dialog titled "Edit Prompt".
  - The warning about locked prompt body is visible.
  - The name field is pre-filled with the current prompt name.
  - After editing and saving, the API returns the updated name.
  */
  test("saved prompt page edit dialog updates prompt name", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    const createResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/prompts`,
      {
        data: {
          name: "Original Name",
          prompt: "Prompt body for editing test.",
          chain_of_thought_instructions: null,
        },
      },
    )
    expect(createResp.ok(), "POST create prompt").toBeTruthy()
    const promptData = (await createResp.json()) as { id: string }
    const promptId = `id::${promptData.id}`

    await page.goto(
      `/prompts/${project.id}/${task.id}/saved/${encodeURIComponent(promptId)}`,
    )

    await expect(
      page.getByRole("heading", { name: "Saved Prompt", exact: true }),
    ).toBeVisible()

    await page.getByRole("button", { name: "Edit" }).click()

    await expect(
      page.getByRole("heading", { name: "Edit Prompt" }),
    ).toBeVisible()

    await expect(
      page.getByText("Prompt body is locked to preserve consistency"),
    ).toBeVisible()

    const nameInput = page.locator("#name")
    await expect(nameInput).toHaveValue("Original Name")

    await nameInput.fill("Updated Name")

    await page.getByRole("button", { name: "Save" }).click()

    await expect
      .poll(async () => {
        const resp = await apiRequest.get(
          `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/prompts`,
        )
        if (!resp.ok()) return null
        const data = (await resp.json()) as {
          prompts: Array<{ id: string; name: string }>
        }
        const found = data.prompts.find((p) => p.id === promptId)
        return found?.name
      })
      .toBe("Updated Name")
  })

  /* @act
  ## Goals
  The clone prompt page loads with a pre-filled form from the source prompt.
  The prompt name is prefixed with "Copy of" and the prompt body matches the
  source prompt.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to create source prompt)

  ## Hints
  - Create a source prompt via the API
  - Navigate to /prompts/{pid}/{tid}/clone/id::{prompt.id}
  - Page title is "Clone Prompt"
  - The form has #prompt_name pre-filled with "Copy of {source_name}"
  - The form has #prompt pre-filled with the source prompt body
  - Submit button says "Clone Prompt"

  ## Assertions
  - Page heading "Clone Prompt" is visible.
  - Prompt name input has value "Copy of {source_name}".
  - Prompt textarea has the source prompt body.
  - "Clone Prompt" submit button is visible.
  */
  test("clone prompt page loads with prefilled form", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    const createResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/prompts`,
      {
        data: {
          name: "Source Prompt",
          prompt: "This is the source prompt body.",
          chain_of_thought_instructions: null,
        },
      },
    )
    expect(createResp.ok(), "POST create source prompt").toBeTruthy()
    const promptData = (await createResp.json()) as { id: string }
    const promptId = `id::${promptData.id}`

    await page.goto(
      `/prompts/${project.id}/${task.id}/clone/${encodeURIComponent(promptId)}`,
    )

    await expect(
      page.getByRole("heading", { name: "Clone Prompt", exact: true }),
    ).toBeVisible()

    await expect(page.locator("#prompt_name")).toHaveValue(
      "Copy of Source Prompt",
    )

    await expect(page.locator("#prompt")).toHaveValue(
      "This is the source prompt body.",
    )

    await expect(
      page.getByRole("button", { name: "Clone Prompt" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Submitting the clone prompt form creates a new prompt and redirects to the
  saved prompt page for the newly created prompt.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to create source prompt)

  ## Hints
  - Create a source prompt via the API
  - Navigate to the clone page
  - Optionally modify the name
  - Click "Clone Prompt" button
  - Page should redirect to /prompts/{pid}/{tid}/saved/id::{new_prompt_id}
  - The saved page shows the new prompt name

  ## Assertions
  - After submission, URL contains /saved/.
  - The saved prompt page heading "Saved Prompt" is visible.
  - The cloned prompt name is visible on the saved page.
  */
  test("clone prompt page submits and redirects to saved prompt", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    const createResp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(task.id)}/prompts`,
      {
        data: {
          name: "Original To Clone",
          prompt: "Clone me please.",
          chain_of_thought_instructions: null,
        },
      },
    )
    expect(createResp.ok(), "POST create source prompt").toBeTruthy()
    const promptData = (await createResp.json()) as { id: string }
    const promptId = `id::${promptData.id}`

    await page.goto(
      `/prompts/${project.id}/${task.id}/clone/${encodeURIComponent(promptId)}`,
    )

    await expect(
      page.getByRole("heading", { name: "Clone Prompt", exact: true }),
    ).toBeVisible()

    await page.locator("#prompt_name").fill("Cloned Version")

    await page.getByRole("button", { name: "Clone Prompt" }).click()

    await page.waitForURL(`**/prompts/${project.id}/${task.id}/saved/**`)

    await expect(
      page.getByRole("heading", { name: "Saved Prompt", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Cloned Version").first()).toBeVisible()
  })
})
