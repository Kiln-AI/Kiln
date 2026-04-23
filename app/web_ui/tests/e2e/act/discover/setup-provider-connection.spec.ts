import { test, expect } from "../../fixtures"
import type { Page } from "@playwright/test"

async function navigateToSetupPage(page: Page, path: string) {
  await page.goto("/setup")
  await expect(
    page.getByRole("heading", { name: "Welcome to Kiln" }),
  ).toBeVisible()
  await page.evaluate((p) => {
    const a = document.createElement("a")
    a.href = p
    a.dataset.sveltekit = ""
    a.style.display = "none"
    document.body.appendChild(a)
    a.click()
    a.remove()
  }, path)
  await page.waitForURL("**" + path)
}

test.describe("Setup provider connection", () => {
  /* @act
  ## Goals
  The connect providers page loads and displays a list of AI providers. OpenRouter should
  be visible and marked as "Recommended". The heading should say "Connect AI Providers".
  In onboarding mode, providers with hide_in_onboarding should not appear (e.g. Kiln Copilot, W&B).

  ## Fixtures
  - cleanBackend

  ## Hints
  - Route is /setup/connect_providers
  - The page heading is "Connect AI Providers"
  - OpenRouter has a "Recommended" badge
  - Each provider row has a "Connect" button

  ## Assertions
  - Page heading "Connect AI Providers" is visible.
  - OpenRouter provider name is visible with "Recommended" badge.
  - OpenAI provider name is visible.
  - Ollama provider name is visible.
  - At least one "Connect" button is visible.
  - Kiln Copilot and Weights & Biases are NOT visible (hidden in onboarding).
  */
  test("connect providers page shows provider list with recommended badge", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend

    await navigateToSetupPage(page, "/setup/connect_providers")

    await expect(
      page.getByRole("heading", { name: "Connect AI Providers" }),
    ).toBeVisible()

    await expect(
      page.getByRole("heading", { name: /OpenRouter\.ai/ }),
    ).toBeVisible()
    await expect(page.getByText("Recommended").first()).toBeVisible()
    await expect(
      page.getByRole("heading", { name: "OpenAI", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("heading", { name: "Ollama", exact: true }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Connect" }).first(),
    ).toBeVisible()

    await expect(
      page.getByRole("heading", { name: "Kiln Copilot" }),
    ).not.toBeVisible()
    await expect(
      page.getByRole("heading", { name: "Weights & Biases" }),
    ).not.toBeVisible()
  })

  /* @act
  ## Goals
  When a mock provider is connected via the connectedMockProvider fixture, the
  connect providers page should show a Continue button that links to /setup/create_project.
  The Custom API provider row should show as connected.

  ## Fixtures
  - cleanBackend
  - connectedMockProvider

  ## Hints
  - Route is /setup/connect_providers
  - Continue button appears when has_connected_providers is true
  - The Continue button links to /setup/create_project
  - connectedMockProvider registers a custom openai_compatible provider

  ## Assertions
  - Continue button is visible.
  - Continue button links to /setup/create_project.
  */
  test("connect providers page shows Continue button when provider connected", async ({
    page,
    cleanBackend,
    connectedMockProvider,
  }) => {
    void cleanBackend
    void connectedMockProvider

    await navigateToSetupPage(page, "/setup/connect_providers")

    const continueButton = page.getByRole("button", { name: "Continue" })
    await expect(continueButton).toBeVisible()

    const link = page.getByRole("link", { name: "Continue" })
    await expect(link).toHaveAttribute("href", "/setup/create_project")
  })

  /* @act
  ## Goals
  Clicking a provider with API key steps (e.g. OpenRouter) shows the API key entry form
  with step instructions, an API Key input field, and a Connect button. Clicking cancel
  returns to the provider list.

  ## Fixtures
  - cleanBackend

  ## Hints
  - Route is /setup/connect_providers
  - Clicking a provider with api_key_steps opens the key entry UI
  - The OpenRouter entry form shows "Connect OpenRouter.ai" heading
  - There is a text input for API Key and a Connect button
  - Cancel link text is "Cancel setting up OpenRouter.ai"

  ## Assertions
  - After clicking OpenRouter Connect, heading "Connect OpenRouter.ai" is visible.
  - An API Key input placeholder is visible.
  - A Connect button is visible in the key entry form.
  - Clicking cancel returns to the provider list view.
  */
  test("clicking provider opens API key entry form", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend

    await navigateToSetupPage(page, "/setup/connect_providers")

    await expect(
      page.getByRole("heading", { name: /OpenRouter\.ai/ }),
    ).toBeVisible()

    const openRouterRow = page
      .getByRole("heading", { name: /OpenRouter\.ai/ })
      .locator("../..")
      .getByRole("button", { name: "Connect" })
    await openRouterRow.click()

    await expect(
      page.getByRole("heading", { name: "Connect OpenRouter.ai" }),
    ).toBeVisible()

    await expect(page.getByPlaceholder("API Key")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Connect" }).first(),
    ).toBeVisible()

    await page.getByText("Cancel setting up OpenRouter.ai").click()

    await expect(
      page.getByRole("heading", { name: /OpenRouter\.ai/ }),
    ).toBeVisible()
    await expect(
      page.getByRole("heading", { name: "Connect OpenRouter.ai" }),
    ).not.toBeVisible()
  })

  /* @act
  ## Goals
  The Kiln Copilot setup page renders its heading, the Connect Kiln Copilot steps UI,
  a cancel link, and a Back button linking to /setup/connect_providers. This page uses
  Kinde OAuth so we only test UI rendering, not the actual OAuth flow.

  ## Fixtures
  - cleanBackend

  ## Hints
  - Route is /setup/connect_providers/kiln_copilot
  - Page has heading "Connect AI Providers"
  - Back button links to /setup/connect_providers
  - Cancel link text is "Cancel setting up Kiln Copilot"

  ## Assertions
  - Page heading "Connect AI Providers" is visible.
  - "Cancel setting up Kiln Copilot" link is visible.
  - Back button links to /setup/connect_providers.
  */
  test("kiln copilot setup page renders heading and back button", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend

    await navigateToSetupPage(page, "/setup/connect_providers/kiln_copilot")

    await expect(
      page.getByRole("heading", { name: "Connect AI Providers" }),
    ).toBeVisible()

    await expect(page.getByText("Cancel setting up Kiln Copilot")).toBeVisible()

    const backLink = page.getByRole("link", { name: "Back" })
    await expect(backLink).toBeVisible()
    await expect(backLink).toHaveAttribute("href", "/setup/connect_providers")
  })

  /* @act
  ## Goals
  The register work page shows a form with Full Name and Work Email fields, a Continue
  submit button, and a "switch to personal non-commercial use" link.

  ## Fixtures
  - cleanBackend

  ## Hints
  - Route is /setup/register_work
  - Page heading is "Register for Work Use"
  - Full Name input has id="full_name"
  - Work Email input has id="email"
  - Submit button label is "Continue"
  - Switch link text contains "switch to personal non-commercial use"

  ## Assertions
  - Page heading "Register for Work Use" is visible.
  - Full Name input is visible and empty.
  - Work Email input is visible and empty.
  - Continue submit button is visible.
  - "switch to personal non-commercial use" link is visible.
  */
  test("register work page shows form fields for name and email", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend

    await navigateToSetupPage(page, "/setup/register_work")

    await expect(
      page.getByRole("heading", { name: "Register for Work Use" }),
    ).toBeVisible()

    const nameInput = page.locator("#full_name")
    await expect(nameInput).toBeVisible()
    await expect(nameInput).toHaveValue("")

    const emailInput = page.locator("#email")
    await expect(emailInput).toBeVisible()
    await expect(emailInput).toHaveValue("")

    await expect(page.getByRole("button", { name: "Continue" })).toBeVisible()

    await expect(
      page.getByText("switch to personal non-commercial use"),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  When a personal email domain (e.g. gmail.com) is entered in the work email field and
  the form is submitted, the page shows a warning about personal email addresses and a
  checkbox to attest it is a work email.

  ## Fixtures
  - cleanBackend

  ## Hints
  - Route is /setup/register_work
  - Fill full_name and email fields, then click Continue
  - Personal domains like @gmail.com trigger the warning
  - Warning text contains "This looks like a personal email address"
  - A checkbox labeled "This is my work email address" appears

  ## Assertions
  - Warning about personal email is visible after submitting with @gmail.com.
  - Checkbox "This is my work email address" appears.
  */
  test("register work page detects personal email and shows warning", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend

    await navigateToSetupPage(page, "/setup/register_work")

    await page.locator("#full_name").fill("Test User")
    await page.locator("#email").fill("test@gmail.com")

    await page.getByRole("button", { name: "Continue" }).click()

    await expect(
      page.getByText("This looks like a personal email address"),
    ).toBeVisible()

    await expect(page.getByText("This is my work email address")).toBeVisible()
  })

  /* @act
  ## Goals
  The support/spread the word page shows a "Star us on GitHub" button, and a continue
  button that initially says "Continue Without Starring" and links to /setup/connect_providers.

  ## Fixtures
  - cleanBackend

  ## Hints
  - Route is /setup/support
  - Page heading is "Spread the Word"
  - Star button text is "Star us on GitHub"
  - Continue button text starts as "Continue Without Starring"
  - Continue links to /setup/connect_providers

  ## Assertions
  - Page heading "Spread the Word" is visible.
  - "Star us on GitHub" button/card is visible.
  - Continue button with text "Continue Without Starring" is visible.
  - Continue link points to /setup/connect_providers.
  */
  test("support page shows star CTA and continue button", async ({
    page,
    cleanBackend,
  }) => {
    void cleanBackend

    await navigateToSetupPage(page, "/setup/support")

    await expect(
      page.getByRole("heading", { name: "Spread the Word" }),
    ).toBeVisible()

    await expect(page.getByText("Star us on GitHub")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Continue Without Starring" }),
    ).toBeVisible()

    const continueLink = page.getByRole("link", {
      name: "Continue Without Starring",
    })
    await expect(continueLink).toHaveAttribute(
      "href",
      "/setup/connect_providers",
    )
  })
})
