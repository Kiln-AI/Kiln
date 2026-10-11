// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest"
import {
  render,
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/svelte"
import * as svelteMod from "svelte"

vi.mock("$lib/api_client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn().mockResolvedValue({
      data: null,
      error: { message: "not running" },
    }),
  },
  base_url: "http://localhost:8757",
}))

vi.mock("$lib/stores", () => ({
  clear_available_models_cache: vi.fn(),
}))

vi.mock("$lib/stores/copilot_connection_store", () => ({
  setCopilotConnected: vi.fn(),
}))

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
  beforeNavigate: vi.fn(),
}))

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

import ConnectProviders from "./connect_providers.svelte"

const invalid_key_message = "Failed to connect to OpenAI. Invalid API key."

const mock_fetch = vi.fn(async (url: string, _init?: RequestInit) => {
  if (url.includes("/api/settings")) {
    return { status: 200, json: async () => ({}) } as unknown as Response
  }
  if (url.includes("/api/provider/connect_api_key")) {
    return {
      status: 401,
      json: async () => ({ message: invalid_key_message }),
    } as unknown as Response
  }
  throw new Error("Unexpected fetch: " + url)
})

beforeEach(() => {
  vi.stubGlobal("fetch", mock_fetch)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

// Svelte 4 async onMount callbacks do not execute in jsdom/vitest,
// so we capture onMount callbacks via vi.spyOn and invoke them manually.
async function render_connect_providers() {
  const on_mount_callbacks: Array<() => unknown> = []
  const spy = vi
    .spyOn(svelteMod, "onMount")
    .mockImplementation((fn: () => unknown) => {
      on_mount_callbacks.push(fn)
    })

  render(ConnectProviders)

  spy.mockRestore()

  for (const callback of on_mount_callbacks) {
    await callback()
  }
  await svelteMod.tick()
}

async function open_provider_dialog(provider_name: string) {
  const provider_row = screen.getByAltText(provider_name)
    .parentElement as HTMLElement
  await fireEvent.click(
    within(provider_row).getByRole("button", { name: "Connect" }),
  )
}

async function submit_api_key(key: string) {
  await fireEvent.input(screen.getByPlaceholderText("API Key"), {
    target: { value: key },
  })
  await fireEvent.click(screen.getByRole("button", { name: "Connect" }))
}

async function fail_openai_connection() {
  await open_provider_dialog("OpenAI")
  await submit_api_key("bad-key")
  await waitFor(() =>
    expect(screen.getByText(invalid_key_message)).toBeTruthy(),
  )
  await fireEvent.click(
    screen.getByRole("button", { name: "Cancel setting up OpenAI" }),
  )
}

describe("ConnectProviders API key dialog", () => {
  it("does not leak a failed provider's error into another provider's dialog", async () => {
    await render_connect_providers()
    await fail_openai_connection()

    await open_provider_dialog("OpenRouter.ai")

    expect(screen.getByText("Connect OpenRouter.ai")).toBeTruthy()
    expect(screen.queryByText(invalid_key_message)).toBeNull()
  })

  it("does not show a stale error when reopening the same provider's dialog", async () => {
    await render_connect_providers()
    await fail_openai_connection()

    await open_provider_dialog("OpenAI")

    expect(screen.queryByText(invalid_key_message)).toBeNull()
  })

  it("clears the missing field highlight when a dialog is reopened", async () => {
    await render_connect_providers()

    await open_provider_dialog("OpenAI")
    await fireEvent.click(screen.getByRole("button", { name: "Connect" }))
    expect(
      screen.getByPlaceholderText("API Key").classList.contains("input-error"),
    ).toBe(true)

    await fireEvent.click(
      screen.getByRole("button", { name: "Cancel setting up OpenAI" }),
    )
    await open_provider_dialog("OpenAI")

    expect(
      screen.getByPlaceholderText("API Key").classList.contains("input-error"),
    ).toBe(false)
  })

  it("closes the dialog and clears the error after a successful connection", async () => {
    await render_connect_providers()

    await open_provider_dialog("OpenAI")
    await submit_api_key("bad-key")
    await waitFor(() =>
      expect(screen.getByText(invalid_key_message)).toBeTruthy(),
    )

    mock_fetch.mockImplementationOnce(
      async () =>
        ({ status: 200, json: async () => ({}) }) as unknown as Response,
    )
    await submit_api_key("good-key")

    await waitFor(() => expect(screen.queryByText("Connect OpenAI")).toBeNull())
    expect(screen.queryByText(invalid_key_message)).toBeNull()
  })

  it("shows TypeSafe AI as connected when a TypeSafe API key is already saved", async () => {
    mock_fetch.mockImplementationOnce(
      async () =>
        ({
          status: 200,
          json: async () => ({ typesafe_api_key: "saved-key" }),
        }) as unknown as Response,
    )

    await render_connect_providers()

    const provider_row = screen.getByAltText("TypeSafe AI")
      .parentElement as HTMLElement
    expect(within(provider_row).getByAltText("Connected")).toBeTruthy()
  })
})

const cloudflare_description = "Open models on the edge, plus an AI gateway."
const cloudflare_token_field = "API Token"
const cloudflare_account_field = "Account ID"
const cloudflare_gateway_field = "AI Gateway ID - Optional"

function mock_saved_settings(settings: Record<string, string>) {
  mock_fetch.mockImplementationOnce(
    async () =>
      ({
        status: 200,
        json: async () => settings,
      }) as unknown as Response,
  )
}

function cloudflare_row(): HTMLElement {
  return screen.getByAltText("Cloudflare").parentElement as HTMLElement
}

async function fill_field(placeholder: string, value: string) {
  await fireEvent.input(screen.getByPlaceholderText(placeholder), {
    target: { value },
  })
}

function connect_request_bodies(): unknown[] {
  return mock_fetch.mock.calls
    .filter(([url]) => url.includes("/api/provider/connect_api_key"))
    .map(([, init]) => JSON.parse(init?.body as string))
}

describe("ConnectProviders Cloudflare", () => {
  it("renders the Cloudflare card with its logo and description", async () => {
    await render_connect_providers()

    const image = screen.getByAltText("Cloudflare") as HTMLImageElement
    expect(image.getAttribute("src")).toBe("/images/cloudflare.svg")
    expect(
      within(cloudflare_row()).getByText(cloudflare_description),
    ).toBeTruthy()
    expect(
      within(cloudflare_row()).getByRole("button", { name: "Connect" }),
    ).toBeTruthy()
  })

  it("shows the three fields, the steps and the Workers Paid warning", async () => {
    await render_connect_providers()
    await open_provider_dialog("Cloudflare")

    expect(screen.getByText("Connect Cloudflare")).toBeTruthy()
    expect(
      screen.getByText("Some models require Cloudflare's Workers Paid plan."),
    ).toBeTruthy()
    const inputs = Array.from(
      document.querySelectorAll("#api-key-fields input"),
    ).map((input) => input.getAttribute("placeholder"))
    expect(inputs).toEqual([
      cloudflare_token_field,
      cloudflare_account_field,
      cloudflare_gateway_field,
    ])
    expect(screen.getAllByRole("listitem")).toHaveLength(5)
    const dashboard_url =
      "https://dash.cloudflare.com/?to=/:account/ai/workers-ai"
    expect(
      screen.getByRole("link", { name: dashboard_url }).getAttribute("href"),
    ).toBe(dashboard_url)
  })

  it("submits the token and account ID without the empty gateway field", async () => {
    await render_connect_providers()
    await open_provider_dialog("Cloudflare")

    await fill_field(cloudflare_token_field, "token")
    await fill_field(cloudflare_account_field, "account")
    mock_fetch.mockImplementationOnce(
      async () =>
        ({
          status: 200,
          json: async () => ({ message: "Connected to Cloudflare" }),
        }) as unknown as Response,
    )
    await fireEvent.click(screen.getByRole("button", { name: "Connect" }))

    await waitFor(() =>
      expect(screen.queryByText("Connect Cloudflare")).toBeNull(),
    )
    expect(connect_request_bodies()).toEqual([
      {
        provider: "cloudflare",
        key_data: {
          [cloudflare_token_field]: "token",
          [cloudflare_account_field]: "account",
        },
      },
    ])
    expect(within(cloudflare_row()).getByAltText("Connected")).toBeTruthy()
  })

  it("submits the gateway ID when one is entered", async () => {
    await render_connect_providers()
    await open_provider_dialog("Cloudflare")

    await fill_field(cloudflare_token_field, "token")
    await fill_field(cloudflare_account_field, "account")
    await fill_field(cloudflare_gateway_field, "default")
    mock_fetch.mockImplementationOnce(
      async () =>
        ({
          status: 200,
          json: async () => ({ message: "Connected to Cloudflare" }),
        }) as unknown as Response,
    )
    await fireEvent.click(screen.getByRole("button", { name: "Connect" }))

    await waitFor(() => expect(connect_request_bodies()).toHaveLength(1))
    expect(connect_request_bodies()[0]).toEqual({
      provider: "cloudflare",
      key_data: {
        [cloudflare_token_field]: "token",
        [cloudflare_account_field]: "account",
        [cloudflare_gateway_field]: "default",
      },
    })
    expect(within(cloudflare_row()).getByAltText("Connected")).toBeTruthy()
  })

  it("does not submit when the account ID is missing", async () => {
    await render_connect_providers()
    await open_provider_dialog("Cloudflare")

    await fill_field(cloudflare_token_field, "token")
    await fireEvent.click(screen.getByRole("button", { name: "Connect" }))

    expect(connect_request_bodies()).toEqual([])
    expect(
      screen
        .getByPlaceholderText(cloudflare_account_field)
        .classList.contains("input-error"),
    ).toBe(true)
  })

  it("shows Cloudflare as connected when the token and account ID are saved", async () => {
    mock_saved_settings({
      cloudflare_api_key: "saved-token",
      cloudflare_account_id: "saved-account",
    })

    await render_connect_providers()

    expect(within(cloudflare_row()).getByAltText("Connected")).toBeTruthy()
  })

  it.each([
    [{ cloudflare_api_key: "saved-token" }],
    [{ cloudflare_account_id: "saved-account" }],
    [{ cloudflare_ai_gateway_id: "default" }],
  ])(
    "does not show Cloudflare as connected with only %o saved",
    async (settings) => {
      mock_saved_settings(settings)

      await render_connect_providers()

      expect(within(cloudflare_row()).queryByAltText("Connected")).toBeNull()
      expect(
        within(cloudflare_row()).getByRole("button", { name: "Connect" }),
      ).toBeTruthy()
    },
  )
})
