import { test, expect } from "../../fixtures"

test.describe("Setup wizard flow", () => {
  /* @act
  ## Goals
  Verify the setup welcome page renders branding elements and a Get Started link
  that points to /setup/intro.

  ## Fixtures
  - cleanBackend

  ## Hints
  - The welcome page is at /setup and shows "Welcome to Kiln" heading, animated logo,
    and a "Get Started" link styled as a button.

  ## Assertions
  - The heading "Welcome to Kiln" is visible.
  - The "Get Started" link is visible and has href /setup/intro.
  - The license agreement link is visible.
  */
  test("welcome page shows branding and Get Started link", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend
    await page.goto("/setup")

    await expect(
      page.getByRole("heading", { name: "Welcome to Kiln" }),
    ).toBeVisible()

    const getStarted = page.getByRole("link", { name: "Get Started" })
    await expect(getStarted).toBeVisible()
    await expect(getStarted).toHaveAttribute("href", "/setup/intro")

    await expect(
      page.getByRole("link", { name: "License Agreement" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Verify the intro tutorial can be navigated through all sections using the
  forward arrow, and that the Continue button appears on the last section.

  ## Fixtures
  - cleanBackend

  ## Hints
  - Navigate to /setup first, then click Get Started to reach the intro page.
  - The tutorial has 5 sections. The forward arrow is a button on the right side.
  - Click it 4 times to reach the last section.
  - When on the last section, a "Continue" button appears linking to /setup/select_account.
  - Before completing, a "Skip Tutorial" link is shown instead.

  ## Assertions
  - The first tutorial section title "Build AI Systems in Minutes" is visible.
  - After advancing through all sections, the Continue button is visible.
  */
  test("intro tutorial can be navigated and shows Continue on last section", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend
    await page.goto("/setup")

    await page.getByRole("link", { name: "Get Started" }).click()

    // Should show Skip Tutorial initially, not Continue
    await expect(
      page.getByRole("link", { name: "Skip Tutorial" }),
    ).toBeVisible()

    // The first tutorial section should be visible
    await expect(page.getByText("Build AI Systems in Minutes")).toBeVisible()

    // Navigate through all 5 sections (click forward 4 times)
    // The forward button is the last SVG button (right arrow)
    for (let i = 0; i < 4; i++) {
      await page
        .locator("button")
        .filter({ has: page.locator("svg") })
        .last()
        .click()
    }

    // After reaching last section, Continue button should appear
    const continueLink = page.getByRole("link", { name: "Continue" })
    await expect(continueLink).toBeVisible()
  })

  /* @act
  ## Goals
  Verify the Skip Tutorial link on the intro page navigates to the select account page.

  ## Fixtures
  - cleanBackend

  ## Hints
  - Navigate to /setup first, then click Get Started to reach the intro page.
  - The Skip Tutorial link is shown before the tutorial is completed.
  - It links to /setup/select_account.

  ## Assertions
  - Clicking Skip Tutorial navigates to a URL containing /setup/select_account.
  */
  test("intro Skip Tutorial links to select account", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend
    await page.goto("/setup")

    await page.getByRole("link", { name: "Get Started" }).click()

    await expect(
      page.getByRole("link", { name: "Skip Tutorial" }),
    ).toBeVisible()

    await page.getByRole("link", { name: "Skip Tutorial" }).click()

    await expect(page).toHaveURL(/\/setup\/select_account/)
  })

  /* @act
  ## Goals
  Verify the select account page shows Personal and For Work options with
  their descriptions.

  ## Fixtures
  - cleanBackend

  ## Hints
  - Navigate through setup flow: /setup -> Get Started -> Skip Tutorial to reach
    select account page.
  - It has a heading "How do you want to use Kiln?"
  - Two cards: "Personal" and "For Work", each with feature lists.

  ## Assertions
  - The heading "How do you want to use Kiln?" is visible.
  - The "Personal" card heading and "Start Personal" button text are visible.
  - The "For Work" card heading and "Start Work" button text are visible.
  */
  test("select account shows Personal and Work options", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend
    await page.goto("/setup")

    await page.getByRole("link", { name: "Get Started" }).click()
    await page.getByRole("link", { name: "Skip Tutorial" }).click()

    await expect(
      page.getByRole("heading", { name: "How do you want to use Kiln?" }),
    ).toBeVisible()

    await expect(page.getByRole("heading", { name: "Personal" })).toBeVisible()
    await expect(page.getByText("Start Personal")).toBeVisible()

    await expect(page.getByRole("heading", { name: "For Work" })).toBeVisible()
    await expect(page.getByText("Start Work")).toBeVisible()
  })

  /* @act
  ## Goals
  Verify that clicking the Personal card on the select account page saves the
  user_type as personal and navigates to the personal registration page.

  ## Fixtures
  - cleanBackend

  ## Hints
  - Navigate through setup flow to reach select account page.
  - The Personal card is a button containing the "Personal" heading.
  - Clicking it calls POST /api/settings with user_type=personal, then navigates
    to /setup/register_personal.

  ## Assertions
  - After clicking, the URL contains /setup/register_personal.
  */
  test("select account Personal card navigates to register personal", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend
    await page.goto("/setup")

    await page.getByRole("link", { name: "Get Started" }).click()
    await page.getByRole("link", { name: "Skip Tutorial" }).click()

    await expect(
      page.getByRole("heading", { name: "How do you want to use Kiln?" }),
    ).toBeVisible()

    await page
      .getByRole("button")
      .filter({ hasText: "Personal" })
      .first()
      .click()

    await expect(page).toHaveURL(/\/setup\/register_personal/)
  })

  /* @act
  ## Goals
  Verify the personal registration form renders with name and email fields
  and a Continue submit button. Also verify the "switch to commercial use" link.

  ## Fixtures
  - cleanBackend

  ## Hints
  - Navigate through setup flow to reach the register personal page by selecting
    the Personal account type.
  - It has a heading "Register for Personal Use".
  - Form fields: #full_name (Full Name) and #email (Email).
  - Submit button label is "Continue".
  - A "switch to commercial use" link is visible at the bottom.

  ## Assertions
  - The heading "Register for Personal Use" is visible.
  - The Full Name and Email fields are present and empty.
  - The Continue button is visible.
  - The "switch to commercial use" text is visible.
  */
  test("register personal page shows form fields and switch link", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend
    await page.goto("/setup")

    await page.getByRole("link", { name: "Get Started" }).click()
    await page.getByRole("link", { name: "Skip Tutorial" }).click()
    await page
      .getByRole("button")
      .filter({ hasText: "Personal" })
      .first()
      .click()

    await expect(
      page.getByRole("heading", { name: "Register for Personal Use" }),
    ).toBeVisible()

    await expect(page.locator("#full_name")).toBeVisible()
    await expect(page.locator("#full_name")).toHaveValue("")

    await expect(page.locator("#email")).toBeVisible()
    await expect(page.locator("#email")).toHaveValue("")

    await expect(page.getByRole("button", { name: "Continue" })).toBeVisible()

    await expect(page.getByText("switch to commercial use")).toBeVisible()
  })
})
