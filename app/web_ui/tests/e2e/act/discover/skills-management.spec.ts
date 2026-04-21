import { test, expect } from "../../fixtures"

test.describe("Skills management", () => {
  /* @act
  ## Goals
  The skills list page loads and shows the empty state when no skills exist,
  including the intro title, description paragraphs, and action buttons.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /skills/{project_id}
  - Empty state shows "Extend your agent with Skills" title
  - Two description paragraphs about domain knowledge and on-demand loading
  - "Add Skill" and "Docs & Guide" buttons visible in empty state
  - "Read the Docs" link in subtitle

  ## Assertions
  - Page heading "Skills" is visible.
  - "Extend your agent with Skills" text is visible.
  - "Add Skill" link/button is visible.
  - "Docs & Guide" link is visible.
  */
  test("skills list page shows empty state", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/skills/${project.id}`)

    await expect(
      page.getByRole("heading", { name: "Skills", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Extend your agent with Skills")).toBeVisible()

    await expect(page.getByRole("link", { name: "Add Skill" })).toBeVisible()

    await expect(page.getByRole("link", { name: "Docs & Guide" })).toBeVisible()
  })

  /* @act
  ## Goals
  The create skill page loads and shows the form with name, description,
  and instructions fields plus the submit button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /skills/{project_id}/create
  - Page title is "Add Skill"
  - Form fields: #skill_name, #skill_description, #skill_body
  - Submit button label is "Add"

  ## Assertions
  - Page heading "Add Skill" is visible.
  - Name input (#skill_name) is visible.
  - Description textarea (#skill_description) is visible.
  - Instructions textarea (#skill_body) is visible.
  - "Add" submit button is visible.
  */
  test("create skill page loads with form", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/skills/${project.id}/create`)

    await expect(
      page.getByRole("heading", { name: "Add Skill", exact: true }),
    ).toBeVisible()

    await expect(page.locator("#skill_name")).toBeVisible()
    await expect(page.locator("#skill_description")).toBeVisible()
    await expect(page.locator("#skill_body")).toBeVisible()

    await expect(page.getByRole("button", { name: "Add" })).toBeVisible()
  })

  /* @act
  ## Goals
  Creating a skill via the form navigates to the skill detail page, and the
  skill then appears in the skills list.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Navigate to /skills/{project_id}/create
  - Fill #skill_name with "test-skill", #skill_description with a description,
    #skill_body with instructions text
  - Click "Add" button
  - After submit, redirects to /skills/{project_id}/{new_skill_id}
  - Navigate to skills list and verify the skill name appears in the table

  ## Assertions
  - After creation, URL contains /skills/{project_id}/ (detail page).
  - Skill detail page heading contains "test-skill".
  - Navigating to the skills list shows "test-skill" in the table.
  */
  test("create skill and verify in list", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    await page.goto(`/skills/${project.id}/create`)

    await page.locator("#skill_name").fill("test-skill")
    await page.locator("#skill_description").fill("A test skill description")
    await page.locator("#skill_body").fill("These are the skill instructions.")

    await page.getByRole("button", { name: "Add" }).click()

    await page.waitForURL(`**/skills/${project.id}/**`)

    await expect(
      page.getByRole("heading", { name: "Skill: test-skill" }),
    ).toBeVisible()

    await page.goto(`/skills/${project.id}`)

    await expect(page.getByText("test-skill")).toBeVisible()
  })

  /* @act
  ## Goals
  The skill detail page loads for an API-seeded skill and displays its
  properties (name, ID) and content (description and body).

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a skill via POST)

  ## Hints
  - Seed a skill via POST /api/projects/{project_id}/skills
  - Route is /skills/{project_id}/{skill_id}
  - Page heading is "Skill: {name}"
  - Properties section shows ID and Name
  - Description and Instructions content sections are visible
  - "Clone" and "Archive" action buttons visible

  ## Assertions
  - Page heading contains the skill name.
  - The skill name is shown in the Properties section.
  - The skill description text is visible.
  - The skill instructions body text is visible.
  - "Clone" button is visible.
  - "Archive" button is visible.
  */
  test("skill detail page shows properties", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const resp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/skills`,
      {
        data: {
          name: "detail-test-skill",
          description: "Detail test description",
          body: "Detail test body content",
        },
      },
    )
    expect(resp.ok()).toBeTruthy()
    const skill = (await resp.json()) as { id: string; name: string }

    await page.goto(`/skills/${project.id}/${skill.id}`)

    await expect(
      page.getByRole("heading", { name: "Skill: detail-test-skill" }),
    ).toBeVisible()

    await expect(
      page.getByText("detail-test-skill", { exact: true }),
    ).toBeVisible()
    await expect(page.getByText("Detail test description")).toBeVisible()
    await expect(page.getByText("Detail test body content")).toBeVisible()

    await expect(page.getByRole("button", { name: "Clone" })).toBeVisible()

    await expect(page.getByRole("button", { name: "Archive" })).toBeVisible()
  })

  /* @act
  ## Goals
  Archiving a skill on the detail page shows the archived warning and changes
  the button to "Unarchive". Unarchiving removes the warning and restores
  the "Archive" button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a skill via POST)

  ## Hints
  - Seed a skill via POST /api/projects/{project_id}/skills
  - Navigate to /skills/{project_id}/{skill_id}
  - Click "Archive" button
  - Archived state shows a warning with "This skill is archived"
  - Status badge changes and button becomes "Unarchive"
  - Click "Unarchive" to restore

  ## Assertions
  - After archiving, "This skill is archived" warning text is visible.
  - "Unarchive" button is visible after archiving.
  - After unarchiving, "This skill is archived" warning is not visible.
  - "Archive" button is visible after unarchiving.
  */
  test("skill detail page archive and unarchive", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const resp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/skills`,
      {
        data: {
          name: "archive-test-skill",
          description: "Archive test description",
          body: "Archive test body",
        },
      },
    )
    expect(resp.ok()).toBeTruthy()
    const skill = (await resp.json()) as { id: string }

    await page.goto(`/skills/${project.id}/${skill.id}`)

    await expect(
      page.getByRole("heading", { name: "Skill: archive-test-skill" }),
    ).toBeVisible()

    await page.getByRole("button", { name: "Archive" }).click()

    await expect(page.getByText("This skill is archived")).toBeVisible()

    await expect(page.getByRole("button", { name: "Unarchive" })).toBeVisible()

    await page.getByRole("button", { name: "Unarchive" }).click()

    await expect(page.getByText("This skill is archived")).not.toBeVisible()

    await expect(page.getByRole("button", { name: "Archive" })).toBeVisible()
  })

  /* @act
  ## Goals
  The clone skill page pre-fills the form with the source skill data,
  prefixing the name with "copy-of-".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask
  - apiRequest (to seed a skill via POST)

  ## Hints
  - Seed a skill via POST /api/projects/{project_id}/skills
  - Route is /skills/{project_id}/clone/{skill_id}
  - Page title is "Clone Skill"
  - Form fields pre-filled: name="copy-of-{original_name}",
    description and body match original
  - Submit button label is "Clone"

  ## Assertions
  - Page heading "Clone Skill" is visible.
  - Name input has value "copy-of-{original_name}".
  - Description textarea has the original description.
  - Instructions textarea has the original body.
  - "Clone" submit button is visible.
  */
  test("clone skill page pre-fills form", async ({
    page,
    apiRequest,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    const { project } = seededProjectWithTask

    const resp = await apiRequest.post(
      `/api/projects/${encodeURIComponent(project.id)}/skills`,
      {
        data: {
          name: "clone-source-skill",
          description: "Clone source description",
          body: "Clone source body content",
        },
      },
    )
    expect(resp.ok()).toBeTruthy()
    const skill = (await resp.json()) as { id: string }

    await page.goto(`/skills/${project.id}/clone/${skill.id}`)

    await expect(
      page.getByRole("heading", { name: "Clone Skill" }),
    ).toBeVisible()

    await expect(page.locator("#skill_name")).toHaveValue(
      "copy-of-clone-source-skill",
    )
    await expect(page.locator("#skill_description")).toHaveValue(
      "Clone source description",
    )
    await expect(page.locator("#skill_body")).toHaveValue(
      "Clone source body content",
    )

    await expect(page.getByRole("button", { name: "Clone" })).toBeVisible()
  })
})
