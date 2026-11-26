// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import Page from "./+page.svelte"
import { BASE_PROMPT } from "./connect_agent"

let test_origin = "http://localhost:8757"

vi.mock("./connect_agent", async (importOriginal) => {
  const original = await importOriginal<typeof import("./connect_agent")>()
  return { ...original, app_origin: () => test_origin }
})

const write_text = vi.fn<[string], Promise<void>>()

function stub_clipboard(clipboard: Clipboard) {
  Object.defineProperty(navigator, "clipboard", {
    value: clipboard,
    configurable: true,
  })
}

beforeEach(() => {
  test_origin = "http://localhost:8757"
  write_text.mockReset()
  write_text.mockResolvedValue(undefined)
  stub_clipboard({ writeText: write_text } as unknown as Clipboard)
})

afterEach(() => {
  cleanup()
})

describe("Connect Your Agent page: addresses", () => {
  it("shows the base prompt and the default MCP URL on the default address", () => {
    const { getByTestId } = render(Page)
    expect(getByTestId("connect-agent-prompt").textContent?.trim()).toBe(
      BASE_PROMPT,
    )
    expect(getByTestId("connect-agent-mcp-url").textContent?.trim()).toBe(
      "http://localhost:8757/mcp",
    )
  })

  it("treats 127.0.0.1 on the default port as the default, but shows its real URL", () => {
    test_origin = "http://127.0.0.1:8757"
    const { getByTestId } = render(Page)
    expect(getByTestId("connect-agent-prompt").textContent?.trim()).toBe(
      BASE_PROMPT,
    )
    expect(getByTestId("connect-agent-mcp-url").textContent?.trim()).toBe(
      "http://127.0.0.1:8757/mcp",
    )
  })

  it("names the real MCP URL in the prompt on another address", () => {
    test_origin = "http://localhost:9000"
    const { getByTestId } = render(Page)
    const prompt = getByTestId("connect-agent-prompt").textContent?.trim()
    expect(
      prompt?.endsWith(
        "\n\nThe Kiln MCP server is at http://localhost:9000/mcp.",
      ),
    ).toBe(true)
    expect(getByTestId("connect-agent-mcp-url").textContent?.trim()).toBe(
      "http://localhost:9000/mcp",
    )
  })
})

describe("Connect Your Agent page: content", () => {
  it("has the title, subtitle and a breadcrumb back to Settings, and no docs link", () => {
    const { container, getByText, queryByText } = render(Page)
    expect(container.querySelector("h1")?.textContent?.trim()).toBe(
      "Connect Your Agent",
    )
    expect(
      getByText("Use Kiln from Claude Code, Codex, and other agents."),
    ).toBeTruthy()
    expect(queryByText("Read the Docs")).toBeNull()
    const breadcrumb = container.querySelector(".breadcrumbs a")
    expect(breadcrumb?.textContent?.trim()).toBe("Settings")
    expect(breadcrumb?.getAttribute("href")).toBe("/settings")
  })

  it("labels the prompt and says what to do next", () => {
    const { getByText } = render(Page)
    expect(getByText("Setup Prompt")).toBeTruthy()
    expect(
      getByText("Paste this into your agent. Then ask it to work with Kiln."),
    ).toBeTruthy()
  })

  it("keeps Set Up Manually closed by default, with the labelled MCP URL inside", () => {
    const { container, getByTestId, getByText } = render(Page)
    const collapse = container.querySelector(".collapse")
    const toggle = collapse?.querySelector<HTMLInputElement>(
      'input[type="checkbox"]',
    )
    expect(toggle).not.toBeNull()
    expect(toggle?.checked).toBe(false)
    expect(getByText("Set Up Manually")).toBeTruthy()
    expect(getByText("MCP Server URL")).toBeTruthy()
    expect(
      getByText("Add this to your agent as an HTTP MCP server."),
    ).toBeTruthy()
    expect(collapse?.contains(getByTestId("connect-agent-mcp-url"))).toBe(true)
  })

  it("has no primary button", () => {
    const { container } = render(Page)
    expect(container.querySelectorAll(".btn-primary")).toHaveLength(0)
  })
})

describe("Connect Your Agent page: copy", () => {
  function copy_button(wrapper: HTMLElement): HTMLButtonElement {
    const button = wrapper.querySelector("button")
    if (!button) throw new Error("no copy button")
    return button
  }

  it("copies the prompt", async () => {
    const { getByTestId } = render(Page)
    await fireEvent.click(copy_button(getByTestId("connect-agent-prompt")))
    expect(write_text).toHaveBeenCalledTimes(1)
    expect(write_text).toHaveBeenCalledWith(BASE_PROMPT)
  })

  it("copies the prompt with the extra sentence on another address", async () => {
    test_origin = "http://localhost:9000"
    const { getByTestId } = render(Page)
    await fireEvent.click(copy_button(getByTestId("connect-agent-prompt")))
    expect(write_text).toHaveBeenCalledWith(
      BASE_PROMPT + "\n\nThe Kiln MCP server is at http://localhost:9000/mcp.",
    )
  })

  it("copies the MCP URL", async () => {
    const { getByTestId } = render(Page)
    await fireEvent.click(copy_button(getByTestId("connect-agent-mcp-url")))
    expect(write_text).toHaveBeenCalledTimes(1)
    expect(write_text).toHaveBeenCalledWith("http://localhost:8757/mcp")
  })
})
