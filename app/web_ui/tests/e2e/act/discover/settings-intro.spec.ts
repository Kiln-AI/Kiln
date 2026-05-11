import { test, expect } from "../../fixtures"

test.describe("Settings - intro", () => {
  /* @act
  ## Goals
  The settings intro page loads and displays the page title and the first
  tutorial section content.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /settings/intro
  - Page title is "Introduction" rendered by AppPage
  - First tutorial section title is "Build AI Systems in Minutes"
  - First section has promo text about building AI systems

  ## Assertions
  - Page heading "Introduction" is visible.
  - "Build AI Systems in Minutes" text is visible.
  - Promo text "What took weeks now takes minutes." is visible.
  */
  test("settings intro page loads with first tutorial section", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings/intro")

    await expect(
      page.getByRole("heading", { name: "Introduction", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Build AI Systems in Minutes")).toBeVisible()

    await expect(
      page.getByText("What took weeks now takes minutes."),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Clicking the right arrow button navigates the tutorial carousel to the
  next section, showing the second section content.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /settings/intro
  - The right arrow is the second SVG button (next button)
  - Second section title is "Measure and Optimize"
  - Second section promo: "Use Kiln evals to measure your system's quality."

  ## Assertions
  - After clicking the next button, "Measure and Optimize" text is visible.
  - "Use Kiln evals to measure your system's quality." text is visible.
  */
  test("tutorial carousel navigates to next section", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings/intro")

    await expect(page.getByText("Build AI Systems in Minutes")).toBeVisible()

    // Click the right/next arrow button (second button with SVG)
    const buttons = page.locator("button").filter({ has: page.locator("svg") })
    await buttons.nth(1).click()

    await expect(page.getByText("Measure and Optimize")).toBeVisible()

    await expect(
      page.getByText("Use Kiln evals to measure your system's quality."),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Navigating through all tutorial sections reaches the final section
  about the Library and Integrations.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /settings/intro
  - There are 5 sections total; click next 4 times to reach the last
  - Last section title is "Library & Integrations"
  - Last section promo: "Our open-source Python library makes it easy to extend Kiln."

  ## Assertions
  - After navigating to the last section, "Library & Integrations" text is visible.
  - "Our open-source Python library makes it easy to extend Kiln." text is visible.
  */
  test("tutorial carousel navigates through all sections", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings/intro")

    await expect(page.getByText("Build AI Systems in Minutes")).toBeVisible()

    const nextButton = page
      .locator("button")
      .filter({ has: page.locator("svg") })
      .nth(1)

    for (let i = 0; i < 4; i++) {
      await nextButton.click()
    }

    await expect(page.getByText("Library & Integrations")).toBeVisible()

    await expect(
      page.getByText(
        "Our open-source Python library makes it easy to extend Kiln.",
      ),
    ).toBeVisible()
  })
})
