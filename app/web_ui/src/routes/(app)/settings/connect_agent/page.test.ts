// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"
import Page from "./+page.svelte"
import { BASE_PROMPT } from "./connect_agent"

let test_origin = "http://localhost:8757"

vi.mock("./connect_agent", async (importOriginal) => {
  const original = await importOriginal<typeof import("./connect_agent")>()
  return { ...original, app_origin: () => test_origin }
})

const write_text = vi.fn<[string], Promise<void>>()

function stub_clipboard(clipboard: Clipboard | undefined) {
  Object.defineProperty(navigator, "clipboard", {
    value: clipboard,
    configurable: true,
  })
}

async function click_and_settle(button: HTMLElement) {
  await fireEvent.click(button)
  // Let the clipboard promise resolve and Svelte flush the label.
  await Promise.resolve()
  await tick()
}

beforeEach(() => {
  vi.useFakeTimers()
  test_origin = "http://localhost:8757"
  write_text.mockReset()
  write_text.mockResolvedValue(undefined)
  stub_clipboard({ writeText: write_text } as unknown as Clipboard)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
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
      prompt?.endsWith(" The Kiln MCP server is at http://localhost:9000/mcp."),
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
      getByText(
        "Use Kiln from Claude Code, Codex, OpenCode and other coding agents.",
      ),
    ).toBeTruthy()
    expect(queryByText("Read the Docs")).toBeNull()
    const breadcrumb = container.querySelector(".breadcrumbs a")
    expect(breadcrumb?.textContent?.trim()).toBe("Settings")
    expect(breadcrumb?.getAttribute("href")).toBe("/settings")
  })

  it("shows the lead-in and the what-next line", () => {
    const { getByText } = render(Page)
    expect(getByText("Paste this in your agent to get started:")).toBeTruthy()
    expect(
      getByText("Then ask your agent to work with Kiln, or type /kiln."),
    ).toBeTruthy()
  })

  it("keeps Set up manually closed by default", () => {
    const { container } = render(Page)
    const toggle = container.querySelector<HTMLInputElement>(
      '.collapse input[type="checkbox"]',
    )
    expect(toggle).not.toBeNull()
    expect(toggle?.checked).toBe(false)
  })

  it("has exactly one primary button and named Copy buttons", () => {
    const { container, getByRole } = render(Page)
    expect(container.querySelectorAll(".btn-primary")).toHaveLength(1)
    expect(getByRole("button", { name: "Copy prompt" })).toBeTruthy()
    expect(getByRole("button", { name: "Copy MCP server URL" })).toBeTruthy()
  })
})

describe("Connect Your Agent page: copy", () => {
  it("copies the prompt and shows Copied for 1500 ms", async () => {
    const { getByTestId } = render(Page)
    const button = getByTestId("connect-agent-copy-prompt")
    await click_and_settle(button)
    expect(write_text).toHaveBeenCalledTimes(1)
    expect(write_text).toHaveBeenCalledWith(BASE_PROMPT)
    expect(button.textContent?.trim()).toBe("Copied")
    expect(button.getAttribute("aria-label")).toBe("Copied prompt")
    vi.advanceTimersByTime(1499)
    await tick()
    expect(button.textContent?.trim()).toBe("Copied")
    vi.advanceTimersByTime(1)
    await tick()
    expect(button.textContent?.trim()).toBe("Copy")
  })

  it("copies the prompt with the extra sentence on another address", async () => {
    test_origin = "http://localhost:9000"
    const { getByTestId } = render(Page)
    await click_and_settle(getByTestId("connect-agent-copy-prompt"))
    expect(write_text).toHaveBeenCalledWith(
      BASE_PROMPT + " The Kiln MCP server is at http://localhost:9000/mcp.",
    )
  })

  it("copies the MCP URL without changing the prompt button", async () => {
    const { getByTestId } = render(Page)
    const url_button = getByTestId("connect-agent-copy-url")
    const prompt_button = getByTestId("connect-agent-copy-prompt")
    await click_and_settle(url_button)
    expect(write_text).toHaveBeenCalledTimes(1)
    expect(write_text).toHaveBeenCalledWith("http://localhost:8757/mcp")
    expect(url_button.textContent?.trim()).toBe("Copied")
    expect(prompt_button.textContent?.trim()).toBe("Copy")
    vi.advanceTimersByTime(1500)
    await tick()
    expect(url_button.textContent?.trim()).toBe("Copy")
  })

  it("announces the copy to assistive tech", async () => {
    const { getByTestId, container } = render(Page)
    await click_and_settle(getByTestId("connect-agent-copy-url"))
    const live_texts = Array.from(
      container.querySelectorAll('[aria-live="polite"]'),
    ).map((el) => el.textContent)
    expect(live_texts).toContain("Copied MCP server URL")
  })

  it("stays on Copy when the clipboard rejects", async () => {
    write_text.mockRejectedValue(new Error("denied"))
    const { getByTestId } = render(Page)
    const button = getByTestId("connect-agent-copy-prompt")
    await click_and_settle(button)
    expect(button.textContent?.trim()).toBe("Copy")
  })

  it("stays on Copy when the Clipboard API is missing", async () => {
    stub_clipboard(undefined)
    const { getByTestId } = render(Page)
    const button = getByTestId("connect-agent-copy-url")
    await click_and_settle(button)
    expect(button.textContent?.trim()).toBe("Copy")
  })

  it("clears a running timer on unmount", async () => {
    const { getByTestId, unmount } = render(Page)
    await click_and_settle(getByTestId("connect-agent-copy-prompt"))
    expect(vi.getTimerCount()).toBe(1)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
