import { test, expect } from "../../fixtures"

test.describe("Settings - providers and misc", () => {
  /* @act
  ## Goals
  The providers list page loads and displays AI providers including Kiln Copilot
  (which is NOT hidden outside onboarding mode). The page title is "AI Providers"
  and has a "Custom Models" action button linking to /settings/providers/add_models.
  Standard providers like OpenRouter, OpenAI, and Ollama should be visible.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask (provides project context so app layout renders)

  ## Hints
  - Route is /settings/providers
  - Page uses ConnectProviders with onboarding=false, so all providers appear
  - "Custom Models" button in the action bar links to add_models page
  - Breadcrumb shows "Settings"

  ## Assertions
  - Page heading "AI Providers" is visible.
  - OpenRouter provider name is visible.
  - OpenAI provider name is visible.
  - Ollama provider name is visible.
  - Kiln Copilot IS visible (not hidden outside onboarding).
  - "Custom Models" button is visible (renders as a button using goto for navigation).
  */
  test("providers page shows provider list with all providers", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings/providers")

    await expect(
      page.getByRole("heading", { name: "AI Providers", exact: true }),
    ).toBeVisible()

    await expect(
      page.getByRole("heading", { name: /OpenRouter\.ai/ }),
    ).toBeVisible()
    await expect(
      page.getByRole("heading", { name: "OpenAI", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("heading", { name: "Ollama", exact: true }),
    ).toBeVisible()

    // Kiln Copilot has a "Recommended" badge inside the h3, so use regex match
    await expect(
      page.getByRole("heading", { name: /Kiln Copilot/ }),
    ).toBeVisible()

    const customModelsButton = page.getByRole("button", {
      name: "Custom Models",
      exact: true,
    })
    await expect(customModelsButton).toBeVisible()
  })

  /* @act
  ## Goals
  The add models page renders an empty state when no custom models exist. The empty
  state shows an intro with title "Add Custom Models" and an "Add Model" button.
  Breadcrumbs include "Settings".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask (provides project context so app layout renders)

  ## Hints
  - Route is /settings/providers/add_models
  - Empty state uses the Intro component with title "Add Custom Models"
  - The "Add Model" button opens a dialog

  ## Assertions
  - Page heading "Custom Models" is visible.
  - Intro title "Add Custom Models" is visible.
  - "Add Model" button is visible in the empty state.
  */
  test("add models page renders empty state with add model button", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings/providers/add_models")

    await expect(
      page.getByRole("heading", { name: "Custom Models", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Add Custom Models")).toBeVisible()

    // Two "Add Model" buttons exist: one in Intro and one in the (hidden) Dialog
    await expect(
      page.getByRole("button", { name: "Add Model", exact: true }).first(),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Clicking the "Add Model" button on the empty add_models page opens a dialog
  with a form containing Model Provider selector, Model ID input, Display Name input,
  and a collapsible Model Settings section.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask (provides project context so app layout renders)

  ## Hints
  - Route is /settings/providers/add_models
  - Dialog title is "Add Custom Model"
  - Form fields use IDs: model_provider, model_id, display_name
  - Advanced section is a collapsible "Model Settings" area
  - Dialog has Cancel and Add Model buttons

  ## Assertions
  - Dialog heading "Add Custom Model" is visible after clicking Add Model.
  - Model ID input is visible.
  - Display Name input is visible.
  - "Model Settings" collapsible section is visible.
  - Cancel button is visible in the dialog.
  - Add Model submit button is visible in the dialog.
  */
  test("add models page shows add model dialog form", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings/providers/add_models")

    // Wait for the empty state to load (loading spinner to disappear)
    await expect(page.getByText("Add Custom Models")).toBeVisible()

    // Click the Intro's "Add Model" button (first one; the dialog also has one)
    await page
      .getByRole("button", { name: "Add Model", exact: true })
      .first()
      .click()

    await expect(
      page.getByRole("heading", { name: "Add Custom Model" }),
    ).toBeVisible()

    await expect(page.locator("#model_id")).toBeVisible()
    await expect(page.locator("#display_name")).toBeVisible()

    await expect(page.getByText("Model Settings")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Cancel", exact: true }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The Kiln Copilot settings page renders with the heading "Kiln Copilot",
  breadcrumbs to Settings and AI Providers, and the Connect Kiln Copilot UI
  with a Connect button and "Cancel setting up Kiln Copilot" link.
  Since this page uses Kinde OAuth, we only test UI rendering.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask (provides project context so app layout renders)

  ## Hints
  - Route is /settings/providers/kiln_copilot
  - Page heading is "Kiln Copilot"
  - ConnectKilnCopilotSteps renders "Connect Kiln Copilot" heading and a Connect button
  - Cancel link text is "Cancel setting up Kiln Copilot"

  ## Assertions
  - Page heading "Kiln Copilot" is visible.
  - "Connect Kiln Copilot" text is visible.
  - Connect button is visible.
  - "Cancel setting up Kiln Copilot" link is visible.
  */
  test("kiln copilot settings page renders connect UI", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings/providers/kiln_copilot")

    await expect(
      page.getByRole("heading", { name: "Kiln Copilot", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Connect Kiln Copilot")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Connect", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Cancel setting up Kiln Copilot")).toBeVisible()
  })

  /* @act
  ## Goals
  The check for update page renders with heading "Check for Update" and displays
  the current version. The page either shows a loading state initially or resolves
  to show the version information.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask (provides project context so app layout renders)

  ## Hints
  - Route is /settings/check_for_update
  - Page heading is "Check for Update"
  - Subtitle shows "Current Version" followed by the version string
  - The page calls update_update_store on mount which triggers a version check
  - The page shows loading, then either update-available, up-to-date, or error state

  ## Assertions
  - Page heading "Check for Update" is visible.
  - "Current Version" text is visible somewhere on the page.
  */
  test("check for update page renders with current version", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.goto("/settings/check_for_update")

    await expect(
      page.getByRole("heading", { name: "Check for Update", exact: true }),
    ).toBeVisible()

    await expect(page.getByText("Current Version")).toBeVisible()
  })
})
