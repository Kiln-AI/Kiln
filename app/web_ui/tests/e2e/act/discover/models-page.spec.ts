import { test, expect } from "../../fixtures"
import type { Page } from "@playwright/test"

const MOCK_REMOTE_CONFIG = {
  model_list: [
    {
      family: "gpt",
      friendly_name: "GPT-4o",
      name: "gpt_4o",
      featured_rank: 1,
      editorial_notes: "Great general-purpose model",
      providers: [
        {
          name: "openai",
          model_id: "gpt-4o",
          provider_finetune_id: "gpt-4o",
          supports_data_gen: true,
          supports_logprobs: true,
          supports_structured_output: true,
          supports_function_calling: true,
          suggested_for_data_gen: true,
          suggested_for_evals: true,
          suggested_for_uncensored_data_gen: false,
          supports_vision: true,
          supports_doc_extraction: false,
          uncensored: false,
          untested_model: false,
          structured_output_mode: "json_schema",
          reasoning_capable: false,
          multimodal_mime_types: ["image/png", "image/jpeg"],
          deprecated: false,
        },
      ],
    },
    {
      family: "claude",
      friendly_name: "Claude 3.5 Sonnet",
      name: "claude_3_5_sonnet",
      featured_rank: 2,
      editorial_notes: null,
      providers: [
        {
          name: "amazon_bedrock",
          model_id: "anthropic.claude-3-5-sonnet",
          provider_finetune_id: null,
          supports_data_gen: true,
          supports_logprobs: false,
          supports_structured_output: true,
          supports_function_calling: true,
          suggested_for_data_gen: false,
          suggested_for_evals: true,
          suggested_for_uncensored_data_gen: false,
          supports_vision: false,
          supports_doc_extraction: false,
          uncensored: false,
          untested_model: false,
          structured_output_mode: "json_instruction",
          reasoning_capable: false,
          multimodal_mime_types: null,
          deprecated: false,
        },
      ],
    },
    {
      family: "llama",
      friendly_name: "Llama 3.1 70B",
      name: "llama_3_1_70b",
      featured_rank: null,
      editorial_notes: "Open source powerhouse",
      providers: [
        {
          name: "ollama",
          model_id: "llama3.1:70b",
          provider_finetune_id: null,
          supports_data_gen: true,
          supports_logprobs: false,
          supports_structured_output: true,
          supports_function_calling: false,
          suggested_for_data_gen: false,
          suggested_for_evals: false,
          suggested_for_uncensored_data_gen: false,
          supports_vision: false,
          supports_doc_extraction: false,
          uncensored: false,
          untested_model: false,
          structured_output_mode: "json_instruction",
          reasoning_capable: false,
          multimodal_mime_types: null,
          deprecated: false,
        },
      ],
    },
    {
      family: "gemini",
      friendly_name: "Gemini 2.0 Flash",
      name: "gemini_2_0_flash",
      featured_rank: null,
      editorial_notes: null,
      providers: [
        {
          name: "google_ai_studio",
          model_id: "gemini-2.0-flash",
          provider_finetune_id: null,
          supports_data_gen: true,
          supports_logprobs: true,
          supports_structured_output: true,
          supports_function_calling: true,
          suggested_for_data_gen: false,
          suggested_for_evals: false,
          suggested_for_uncensored_data_gen: false,
          supports_vision: true,
          supports_doc_extraction: true,
          uncensored: false,
          untested_model: false,
          structured_output_mode: "json_schema",
          reasoning_capable: true,
          multimodal_mime_types: ["image/png"],
          deprecated: false,
        },
      ],
    },
  ],
}

const MOCK_PRICING_DATA = {
  openai: {
    models: {
      "gpt-4o": {
        cost: { input: 2.5, output: 10 },
      },
    },
  },
}

async function setupMockRoutes(page: Page) {
  await page.route("**/remote-config.getkiln.ai/kiln_config_v2.json", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_REMOTE_CONFIG),
    }),
  )
  await page.route("**/models.dev/api.json", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_PRICING_DATA),
    }),
  )
}

test.describe("Models page", () => {
  /* @act
  ## Goals
  The models page loads and displays the page header with title "Model Library",
  subtitle "Browse our built-in models", and action buttons for "Custom Models"
  and "Manage Providers".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Route is /models
  - The page uses AppPage with title "Model Library"
  - Action buttons link to /settings/providers/add_models and /settings/providers
  - "Read the Docs" link goes to models docs

  ## Assertions
  - Page heading "Model Library" is visible.
  - "Custom Models" link is visible.
  - "Manage Providers" link is visible.
  - "Read the Docs" link is visible.
  */
  test("page header shows title and action buttons", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Custom Models" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Manage Providers" }),
    ).toBeVisible()

    await expect(
      page.getByRole("link", { name: "Read the Docs" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The models page loads with featured filter active by default and shows
  model cards for featured models. The results count reflects filtered models.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Default capability filter is "featured" which filters to models with featured_rank != null
  - GPT-4o (rank 1) and Claude 3.5 Sonnet (rank 2) are featured in mock data
  - Llama 3.1 70B and Gemini 2.0 Flash have no featured_rank
  - Results text says "Showing N of M models"

  ## Assertions
  - GPT-4o model card is visible.
  - Claude 3.5 Sonnet model card is visible.
  - Llama 3.1 70B model card is NOT visible (not featured).
  - Results count shows "Showing 2 of 4 models".
  */
  test("default featured filter shows only featured models", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    await expect(page.getByText("Showing 2 of 4 models")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "GPT-4o", exact: true }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Claude 3.5 Sonnet", exact: true }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Llama 3.1 70B", exact: true }),
    ).not.toBeVisible()
  })

  /* @act
  ## Goals
  Clicking the "See All N Models" button clears the featured filter and shows
  all available models.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The "See All 4 Models" button appears at the bottom when featured filter is active
  - Clicking it sets selectedCapability to empty string
  - After clearing, all 4 models should be visible

  ## Assertions
  - "See All 4 Models" button is visible initially.
  - After clicking it, results count shows "Showing 4 of 4 models".
  - Llama 3.1 70B and Gemini 2.0 Flash become visible.
  */
  test("see all models button clears featured filter", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    const seeAllBtn = page.getByRole("button", { name: "See All 4 Models" })
    await expect(seeAllBtn).toBeVisible()
    await seeAllBtn.click()

    await expect(page.getByText("Showing 4 of 4 models")).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Llama 3.1 70B" }),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Gemini 2.0 Flash" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The search input filters models by name as the user types.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The search input has id="search" and placeholder "Search by name, model ID..."
  - Typing "gpt" should filter to only GPT-4o
  - First clear the featured filter by clicking "See All" to see all models

  ## Assertions
  - After typing "gpt" in search, only GPT-4o is shown.
  - Results count updates to "Showing 1 of 4 models".
  */
  test("search input filters models by name", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    await page.getByRole("button", { name: "See All 4 Models" }).click()
    await expect(page.getByText("Showing 4 of 4 models")).toBeVisible()

    await page.locator("#search").fill("llama")

    await expect(page.getByText("Showing 1 of 4 models")).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Llama 3.1 70B" }),
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "GPT-4o" })).not.toBeVisible()
  })

  /* @act
  ## Goals
  When search and filters produce no matching models, the empty state message
  "No models found" is shown with help text.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Enter a search term that matches nothing (e.g., "zzzznotamodel")
  - The empty state shows "No models found" heading and
    "Try adjusting your search or filter criteria." text

  ## Assertions
  - "No models found" text is visible.
  - "Try adjusting your search or filter criteria." text is visible.
  - Results count shows "Showing 0 of 4 models".
  */
  test("empty state shown when no models match search", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    await page.locator("#search").fill("zzzznotamodel")

    await expect(page.getByText("Showing 0 of 4 models")).toBeVisible()
    await expect(page.getByText("No models found")).toBeVisible()
    await expect(
      page.getByText("Try adjusting your search or filter criteria."),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The active filter badges appear when filters are active and can be removed
  by clicking them. The "Clear Filters" button removes all filters.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Active filters show as badges with "Active filters:" label
  - The default "Featured" filter badge is visible
  - Clicking a badge removes that filter
  - "Clear Filters" button removes all active filters

  ## Assertions
  - "Active filters:" label is visible.
  - "Featured" filter badge is visible.
  - After clicking Clear Filters, all models are shown.
  */
  test("clear filters button removes all filters", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    await expect(page.getByText("Active filters:")).toBeVisible()
    await expect(page.getByRole("button", { name: "Featured" })).toBeVisible()

    await page.getByRole("button", { name: "Clear Filters" }).click()

    await expect(page.getByText("Showing 4 of 4 models")).toBeVisible()
  })

  /* @act
  ## Goals
  Model cards display capability badges (e.g., Data Gen, Evals, Structured Output)
  based on model provider capabilities.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - GPT-4o has: suggested_for_data_gen (Data Gen star), suggested_for_evals (Evals star),
    supports_finetuning (Finetune star), supports_structured_output, supports_function_calling (Tools),
    supports_logprobs, supports_vision
  - Badges appear inside the model card

  ## Assertions
  - GPT-4o card shows "Data Gen" badge text.
  - GPT-4o card shows "Evals" badge text.
  - GPT-4o card shows "Finetune" badge text.
  */
  test("model cards display capability badges", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    const gpt4oCard = page.getByRole("button", { name: "GPT-4o", exact: true })
    await expect(gpt4oCard).toBeVisible()

    await expect(
      page.getByText("Finetune", { exact: false }).first(),
    ).toBeVisible()
    await expect(
      page.getByText("Evals", { exact: false }).first(),
    ).toBeVisible()
    await expect(
      page.getByText("Data Gen", { exact: false }).first(),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Model cards show "Available Providers" section with provider names and model IDs.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - Each model card has "Available Providers" heading
  - Provider names come from provider_name_from_id()
  - Model IDs shown as secondary text under provider name
  - Providers not connected show with reduced opacity

  ## Assertions
  - "Available Providers" text is visible on model cards.
  - Provider model IDs like "gpt-4o" are visible.
  */
  test("model cards show available providers", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    await expect(page.getByText("Available Providers").first()).toBeVisible()

    await expect(
      page.getByText("gpt-4o", { exact: true }).first(),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  Clicking a model card when no provider is connected opens a "Connect to Provider"
  dialog with the model name and a list of available providers.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - When no provider is connected, clicking a model card opens the Connect to Provider dialog
  - The dialog shows the model name and a "Connect Provider" button
  - Dialog also has a "Cancel" button

  ## Assertions
  - Dialog heading "Connect to Provider" is visible after clicking a model card.
  - Dialog shows the model friendly name.
  - "Connect Provider" button is visible in the dialog.
  */
  test("clicking unconnected model opens connect provider dialog", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    await page.getByRole("button", { name: "GPT-4o", exact: true }).click()

    await expect(
      page.getByRole("heading", { name: "Connect to Provider" }),
    ).toBeVisible()

    await expect(
      page.getByText("GPT-4o", { exact: false }).first(),
    ).toBeVisible()

    await expect(
      page.getByRole("button", { name: "Connect Provider" }),
    ).toBeVisible()
  })

  /* @act
  ## Goals
  The error state is shown when the remote config fetch fails, with an error
  message and a "Try again" button.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - When fetchModelsFromRemoteConfig fails, error state is shown
  - Error state has "Error loading models" heading and a "Try again" button
  - Mock the remote config endpoint to return a 500 error

  ## Assertions
  - "Error loading models" text is visible.
  - "Try again" button is visible.
  */
  test("error state shown when remote config fetch fails", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask

    await page.route(
      "**/remote-config.getkiln.ai/kiln_config_v2.json",
      (route) => route.fulfill({ status: 500, body: "Server Error" }),
    )
    await page.route("**/models.dev/api.json", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_PRICING_DATA),
      }),
    )

    await page.goto("/models")

    await expect(page.getByText("Error loading models")).toBeVisible()
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible()
  })

  /* @act
  ## Goals
  Model cards show editorial notes when present as secondary text below
  the model name.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - GPT-4o has editorial_notes: "Great general-purpose model"
  - Editorial notes appear as small gray text under the model name
  - Claude 3.5 Sonnet has null editorial_notes

  ## Assertions
  - "Great general-purpose model" text is visible on the GPT-4o card.
  */
  test("model cards show editorial notes", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    await expect(page.getByText("Great general-purpose model")).toBeVisible()
  })

  /* @act
  ## Goals
  Each model card has a "Try" button that navigates to the /run page
  with the model parameter when clicked.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The Try button is inside each model card header
  - Clicking Try calls tryModel which navigates to /run?model=provider/model_name
  - Since no provider is connected, it should open the connect dialog instead
  - The Try button uses stopPropagation to prevent card click

  ## Assertions
  - "Try" button is visible on model cards.
  */
  test("model cards have try button", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    const tryButtons = page.getByRole("button", { name: "Try", exact: true })
    await expect(tryButtons.first()).toBeVisible()
  })

  /* @act
  ## Goals
  Removing a filter badge by clicking it updates the results. The featured
  filter badge can be clicked to remove it, showing all models.

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - The "Featured" badge appears in active filters section
  - Clicking it removes the capability filter
  - After removal, all 4 models should be visible

  ## Assertions
  - Clicking the "Featured" filter badge shows all 4 models.
  - Results count updates to "Showing 4 of 4 models".
  */
  test("removing filter badge updates results", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    await expect(page.getByText("Showing 2 of 4 models")).toBeVisible()

    await page.getByRole("button", { name: "Featured" }).click()

    await expect(page.getByText("Showing 4 of 4 models")).toBeVisible()
  })

  /* @act
  ## Goals
  The page title in the browser tab is "Models - Kiln".

  ## Fixtures
  - registeredUser
  - seededProjectWithTask

  ## Hints
  - svelte:head sets title to "Models - Kiln"

  ## Assertions
  - Browser page title is "Models - Kiln".
  */
  test("page title is Models - Kiln", async ({
    page,
    registeredUser,
    seededProjectWithTask,
  }) => {
    void registeredUser
    void seededProjectWithTask
    await setupMockRoutes(page)

    await page.goto("/models")

    await expect(
      page.getByRole("heading", { name: "Model Library" }),
    ).toBeVisible()

    await expect(page).toHaveTitle("Models - Kiln")
  })
})
