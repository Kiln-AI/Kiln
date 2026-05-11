import { test, expect } from "../../fixtures"

test.describe("Run page", () => {
  /* @act
  ## Goals
  Verify the run page loads with the main structural elements: the page title "Run",
  the "Input" heading, the "Plaintext Input" textarea, and the "Options" heading with
  run configuration controls.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Navigate to /run. The page requires ui_state with project/task IDs (seededProjectWithTask handles this).
  - The "Input" heading is a div with class text-xl.
  - The "Options" heading is also a div with class text-xl.

  ## Assertions
  - The page title "Run" is visible as a heading.
  - The text "Input" is visible.
  - The text "Options" is visible.
  - A "Run" submit button is visible.
  */
  test("run page loads with Input and Options sections", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/run")

    await expect(page.getByRole("heading", { name: "Run" })).toBeVisible()

    await expect(page.getByText("Input", { exact: true })).toBeVisible()
    await expect(page.getByText("Options", { exact: true })).toBeVisible()

    await expect(page.getByRole("button", { name: "Run" })).toBeVisible()
  })

  /* @act
  ## Goals
  Verify the run page displays the current task name in the subtitle area.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The subtitle is formatted as "Task: <task name>".
  - seededProjectWithTask creates a task with a random name.

  ## Assertions
  - Text containing "Task: <seeded task name>" is visible on the page.
  */
  test("run page shows task name in subtitle", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { task } = seededProjectWithTask

    await page.goto("/run")

    await expect(page.getByText(`Task: ${task.name}`)).toBeVisible()
  })

  /* @act
  ## Goals
  Verify the run page shows a plaintext input textarea for tasks without an input
  JSON schema (the default for seeded tasks).

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The textarea label is "Plaintext Input".
  - The textarea has an auto-generated id starting with "plaintext_input_".

  ## Assertions
  - A textarea labeled "Plaintext Input" is visible.
  */
  test("run page shows plaintext input textarea", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/run")

    await expect(page.getByText("Plaintext Input")).toBeVisible()
    await expect(page.locator("textarea")).toBeVisible()
  })

  /* @act
  ## Goals
  Verify the Clear All button clears the plaintext input textarea.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Type something into the textarea, then click the "Clear All" action button.
  - The textarea should be empty after clicking Clear All.

  ## Assertions
  - After filling the textarea and clicking "Clear All", the textarea value is empty.
  */
  test("Clear All button clears the input textarea", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/run")

    const textarea = page.locator("textarea")
    await expect(textarea).toBeVisible()

    await textarea.fill("Some test input data")
    await expect(textarea).toHaveValue("Some test input data")

    await page.getByRole("button", { name: "Clear All" }).click()

    await expect(textarea).toHaveValue("")
  })

  /* @act
  ## Goals
  Verify the model dropdown is visible on the run page and shows the "Model" label
  with a select element that has model option groups.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - connectedMockProvider

  ## Hints
  - The model dropdown uses FormElement with id="model" and label "Model".
  - connectedMockProvider ensures at least one provider with models is available.

  ## Assertions
  - The text "Model" is visible as a label.
  - The model select element (id="model") is visible.
  */
  test("model dropdown is visible with Model label", async ({
    page,
    registeredUser,
    seededProjectWithTask,
    connectedMockProvider,
  }) => {
    void registeredUser
    void seededProjectWithTask
    void connectedMockProvider

    await page.goto("/run")

    await expect(page.getByText("Model", { exact: true })).toBeVisible()
    await expect(page.getByRole("listbox", { name: "Model" })).toBeVisible()
  })

  /* @act
  ## Goals
  Verify the prompt type selector is visible on the run page with the "Prompt" label.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The prompt type selector uses a FormElement with label "Prompt".

  ## Assertions
  - The text "Prompt" is visible on the page.
  */
  test("prompt type selector is visible", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/run")

    await expect(page.getByText("Prompt Method")).toBeVisible()
  })

  /* @act
  ## Goals
  Verify the Advanced Options collapse section can be expanded to reveal temperature
  and top_p controls.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The collapse is a Collapse component with title "Advanced Options".
  - Inside are fields for Temperature and Top P.

  ## Assertions
  - Clicking "Advanced Options" reveals the "Temperature" label.
  - The "Top P" label is also visible after expanding.
  */
  test("Advanced Options collapse expands to show temperature and top_p", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/run")

    await expect(
      page.getByText("Temperature", { exact: true }),
    ).not.toBeVisible()

    const collapseCheckbox = page
      .locator(".collapse", { hasText: "Advanced Options" })
      .locator('input[type="checkbox"]')
    await collapseCheckbox.click({ force: true })

    await expect(page.getByText("Temperature", { exact: true })).toBeVisible()
    await expect(page.getByText("Top P", { exact: true })).toBeVisible()
  })

  /* @act
  ## Goals
  Verify end-to-end task execution: fill in plaintext input, select the mock model,
  click Run, and confirm the output section appears with the canned response.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - connectedMockProvider
  - mockInferenceProvider

  ## Hints
  - Queue a canned response via mockInferenceProvider.queue before running.
  - Select the mock model in the model dropdown (id="model").
  - Fill plaintext input, click Run, and wait for the output section (#output-section) to appear.
  - The output section contains the canned response text.

  ## Assertions
  - After running, the output section is visible.
  - The canned response text appears in the output section.
  */
  test("submitting a run with mock provider shows output", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
    connectedMockProvider,
    mockInferenceProvider,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask
    const cannedContent = `run-page-test-${Date.now()}`

    await mockInferenceProvider.queue({ content: cannedContent })

    await page.goto("/run")

    const textarea = page.locator("textarea")
    await expect(textarea).toBeVisible()
    await textarea.fill("Test input for run page")

    const modelSelect = page.getByRole("listbox", { name: "Model" })
    await expect(modelSelect).toBeVisible()
    await modelSelect.click()
    await page
      .getByRole("option", { name: connectedMockProvider.modelId })
      .click()

    await page.getByRole("button", { name: "Run" }).click()

    const outputSection = page.locator("#output-section")
    await expect(outputSection).toBeVisible({ timeout: 15000 })

    await expect(outputSection.getByText(cannedContent).first()).toBeVisible({
      timeout: 10000,
    })
  })
})
