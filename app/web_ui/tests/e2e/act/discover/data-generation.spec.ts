import { test, expect } from "../../fixtures"

test.describe("Synthetic data generation", () => {
  /* @act
  ## Goals
  The generate overview page loads and displays the intro UI with two options:
  Evals and Fine-Tuning cards. Each card has a button to start generation.
  The page title should be "Synthetic Data Generation".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /generate/{project_id}/{task_id}
  - The page shows a MultiIntro with "Evals" and "Fine-Tuning" cards
  - "Generate Eval Data" button for evals
  - "Generate Fine-Tuning Data" button for fine-tuning
  - Page title is "Synthetic Data Generation"
  - The page may briefly show a loading spinner before showing intro

  ## Assertions
  - Page heading "Synthetic Data Generation" is visible.
  - "Evals" heading is visible.
  - "Fine-Tuning" heading is visible.
  - "Generate Eval Data" button is visible.
  - "Generate Fine-Tuning Data" button is visible.
  */
  test("generate overview shows eval and fine-tuning cards", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/generate/${project.id}/${task.id}`)

    await expect(
      page.getByRole("heading", { name: "Synthetic Data Generation" }),
    ).toBeVisible()

    await expect(
      page.getByRole("heading", { name: "Evals", exact: true }),
    ).toBeVisible()

    await expect(
      page.getByRole("heading", { name: "Fine-Tuning", exact: true }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Generate Eval Data" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Generate Fine-Tuning Data" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Clicking "Generate Eval Data" opens a dialog titled "Generate Synthetic Eval Data"
  which shows a "Create a New Spec" link when no specs exist.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /generate/{project_id}/{task_id}
  - Clicking "Generate Eval Data" calls show_specs_dialog which opens a Dialog
  - When no specs exist, the dialog shows "Create a New Spec" link
  - The link goes to /specs/{project_id}/{task_id}/select_template

  ## Assertions
  - Dialog with heading "Generate Synthetic Eval Data" is visible after clicking button.
  - "Create a New Spec" link is visible inside the dialog.
  */
  test("generate eval data button opens specs dialog with create link", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/generate/${project.id}/${task.id}`)

    await page.getByRole("button", { name: "Generate Eval Data" }).click()

    await expect(
      page.getByRole("heading", { name: "Generate Synthetic Eval Data" }),
    ).toBeVisible()

    const createLink = page.getByRole("link", { name: "Create a New Spec" })
    await expect(createLink).toBeVisible()
    await expect(createLink).toHaveAttribute(
      "href",
      `/specs/${project.id}/${task.id}/select_template`,
    )
  })

  /* @act
  ## Goals
  Clicking "Generate Fine-Tuning Data" with only the default fine_tune_data tag
  redirects directly to the synth page with reason=fine_tune parameters (single
  tag shortcut skips the dialog).

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /generate/{project_id}/{task_id}
  - When there is only the default "fine_tune_data" tag, clicking the button
    skips the dialog and navigates to the synth page with URL params
  - The synth page URL includes reason=fine_tune and template_id=fine_tuning

  ## Assertions
  - After clicking "Generate Fine-Tuning Data", the URL navigates to the synth page.
  - The synth page URL contains reason=fine_tune.
  */
  test("generate fine-tuning data navigates to synth page", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/generate/${project.id}/${task.id}`)

    await expect(
      page.getByRole("button", { name: "Generate Fine-Tuning Data" }),
    ).toBeVisible()

    await page
      .getByRole("button", { name: "Generate Fine-Tuning Data" })
      .click()

    await page.waitForURL(`**/generate/${project.id}/${task.id}/synth**`)

    await expect(page).toHaveURL(/reason=fine_tune/)
  })

  /* @act
  ## Goals
  The synth page loads in fresh state (no saved data) and shows the
  DataGenIntro with "Add Topics" and "Generate Model Inputs" buttons.
  The page title should be "Synthetic Data Generation".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /generate/{project_id}/{task_id}/synth?reason=fine_tune&template_id=fine_tuning&splits=fine_tune_data%3A1
  - When in setup mode with no saved data, shows DataGenIntro
  - DataGenIntro shows "Add Topics" and "Generate Model Inputs" buttons
  - Also has a "Docs & Guide" action button

  ## Assertions
  - Page heading "Synthetic Data Generation" is visible.
  - "Add Topics" button is visible.
  - "Generate Model Inputs" button is visible.
  - "Docs & Guide" link is visible.
  */
  test("synth page shows intro with add topics and generate inputs buttons", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(
      `/generate/${project.id}/${task.id}/synth?reason=fine_tune&template_id=fine_tuning&splits=fine_tune_data%3A1`,
    )

    await expect(
      page.getByRole("heading", { name: "Synthetic Data Generation" }),
    ).toBeVisible()

    await expect(page.getByRole("button", { name: "Add Topics" })).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Generate Model Inputs" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Docs & Guide" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The synth page has a "Docs & Guide" action button and a "Read the Docs"
  sub-subtitle link pointing to the synthetic data generation documentation.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /generate/{project_id}/{task_id}/synth?reason=fine_tune&template_id=fine_tuning&splits=fine_tune_data%3A1
  - "Docs & Guide" is an action button (not a link)
  - "Read the Docs" is a sub-subtitle link with the correct href

  ## Assertions
  - "Docs & Guide" button is visible.
  - "Read the Docs" link has the correct href.
  */
  test("synth page docs link has correct href", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(
      `/generate/${project.id}/${task.id}/synth?reason=fine_tune&template_id=fine_tuning&splits=fine_tune_data%3A1`,
    )

    await expect(
      page.getByRole("heading", { name: "Synthetic Data Generation" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Docs & Guide" }),
    ).toBeVisible()

    const readDocsLink = page.getByRole("link", { name: "Read the Docs" })
    await expect(readDocsLink).toBeVisible()
    await expect(readDocsLink).toHaveAttribute(
      "href",
      "https://docs.kiln.tech/docs/synthetic-data-generation",
    )
  })

  /* @act
  ## Goals
  The QnA generation page loads in empty state and shows the intro UI with
  a "Generate Q&A Data" title and a "Select Documents" button.
  The page heading should be "Synthetic Data Generation".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /generate/{project_id}/{task_id}/qna
  - The empty state shows QnaGenIntro component
  - QnaGenIntro has title "Generate Q&A Data" and "Select Documents" button
  - Page heading is "Synthetic Data Generation"
  - Has a "Docs & Guide" link and "Reset" button in the action bar

  ## Assertions
  - Page heading "Synthetic Data Generation" is visible.
  - "Generate Q&A Data" heading is visible.
  - "Select Documents" button is visible.
  - "Reset" button is visible.
  - "Docs & Guide" link is visible.
  */
  test("qna page shows empty state with select documents button", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/generate/${project.id}/${task.id}/qna`)

    await expect(
      page.getByRole("heading", { name: "Synthetic Data Generation" }),
    ).toBeVisible()

    await expect(page.getByText("Generate Q&A Data")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Select Documents" }),
    ).toBeVisible()

    await expect(page.getByRole("button", { name: "Reset" })).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Docs & Guide" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The QnA page shows a header card with Goal (Evaluation), Template, and Tags
  sections. The goal is always "Evaluation" for QnA, and template defaults to
  "query_answer_generation".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /generate/{project_id}/{task_id}/qna
  - The header card has three sections: Goal, Template, Tags
  - Goal label uses CSS uppercase so HTML text is "Goal"
  - "Evaluation" text appears in the Goal section
  - Template shows "query_answer_generation"
  - Tags shows "No tag assignments" when none are set

  ## Assertions
  - "Goal" label text is visible.
  - "Evaluation" text is visible.
  - "Template" label text is visible.
  - "query_answer_generation" text is visible.
  - "Tags" label text is visible.
  - "No tag assignments" text is visible.
  */
  test("qna page shows header card with goal template and tags", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/generate/${project.id}/${task.id}/qna`)

    await expect(
      page.getByRole("heading", { name: "Synthetic Data Generation" }),
    ).toBeVisible()

    await expect(page.getByText("Goal", { exact: true })).toBeVisible()
    await expect(page.getByText("Evaluation")).toBeVisible()
    await expect(page.getByText("Template", { exact: true })).toBeVisible()
    await expect(page.getByText("query_answer_generation")).toBeVisible()
    await expect(page.getByText("Tags", { exact: true })).toBeVisible()
    await expect(page.getByText("No tag assignments")).toBeVisible()
  })

  /* @act
  ## Goals
  The QnA page has a "Read the Docs" sub-subtitle link pointing to the QnA eval
  documentation and a "Docs & Guide" action button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /generate/{project_id}/{task_id}/qna
  - "Docs & Guide" is an action button (not a link)
  - "Read the Docs" is a sub-subtitle link with the correct href

  ## Assertions
  - "Docs & Guide" button is visible.
  - "Read the Docs" link has the correct href.
  */
  test("qna page docs link has correct href", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/generate/${project.id}/${task.id}/qna`)

    await expect(
      page.getByRole("heading", { name: "Synthetic Data Generation" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Docs & Guide" }),
    ).toBeVisible()

    const readDocsLink = page.getByRole("link", { name: "Read the Docs" })
    await expect(readDocsLink).toBeVisible()
    await expect(readDocsLink).toHaveAttribute(
      "href",
      "https://docs.kiln.tech/docs/evaluations/evaluate-rag-accuracy-q-and-a-evals",
    )
  })

  /* @act
  ## Goals
  The generate overview page has a "Read the Docs" sub-subtitle link and a
  "Docs & Guide" action button, both pointing to the synthetic data
  generation documentation.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /generate/{project_id}/{task_id}
  - "Docs & Guide" is an action button (not a link)
  - "Read the Docs" is a sub-subtitle link with the correct href

  ## Assertions
  - "Docs & Guide" button is visible.
  - "Read the Docs" link has the correct href.
  */
  test("generate overview docs link has correct href", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project, task } = seededProjectWithTask

    await page.goto(`/generate/${project.id}/${task.id}`)

    await expect(
      page.getByRole("heading", { name: "Synthetic Data Generation" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Docs & Guide" }),
    ).toBeVisible()

    const readDocsLink = page.getByRole("link", { name: "Read the Docs" })
    await expect(readDocsLink).toBeVisible()
    await expect(readDocsLink).toHaveAttribute(
      "href",
      "https://docs.kiln.tech/docs/synthetic-data-generation",
    )
  })
})
