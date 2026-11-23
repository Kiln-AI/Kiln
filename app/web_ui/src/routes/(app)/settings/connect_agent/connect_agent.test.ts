import { describe, it, expect, vi, afterEach } from "vitest"
import { readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { base_url } from "$lib/api_client"
import {
  AGENT_INSTALL_GUIDE_URL,
  BASE_PROMPT,
  DEFAULT_ORIGIN,
  app_origin,
  build_prompt,
  is_default_address,
  mcp_url,
} from "./connect_agent"

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../../../..",
)

function read_repo_file(name: string): string {
  return readFileSync(path.join(REPO_ROOT, name), "utf-8")
}

// The stub skill of agent_install.md step 3. A change here is a deliberate change to the stub.
const STUB_SKILL = `---
name: kiln
description: Kiln is an app for building, evaluating and optimizing AI agents. Use when the user asks for /kiln or wants to work with Kiln.
---

Call the \`kiln_skill\` tool from the \`kiln\` MCP server to learn how to use Kiln, then follow what it says.

If the \`kiln_skill\` tool is not available, Kiln is installed but offline: ask the user to start the Kiln app, then try again.`

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("mcp_url", () => {
  it("appends the MCP path to the origin", () => {
    expect(mcp_url(DEFAULT_ORIGIN)).toBe("http://localhost:8757/mcp")
  })

  it("removes trailing slashes from the origin", () => {
    expect(mcp_url("http://localhost:8757/")).toBe("http://localhost:8757/mcp")
    expect(mcp_url("http://localhost:8757//")).toBe("http://localhost:8757/mcp")
  })

  it("keeps a non-default host and port", () => {
    expect(mcp_url("http://127.0.0.1:9000")).toBe("http://127.0.0.1:9000/mcp")
  })
})

describe("is_default_address", () => {
  it.each([
    "http://localhost:8757",
    "http://localhost:8757/",
    "http://127.0.0.1:8757",
    "http://[::1]:8757",
  ])("is true for %s", (origin) => {
    expect(is_default_address(origin)).toBe(true)
  })

  it.each([
    "http://localhost:9000",
    "http://127.0.0.1:9000",
    "https://localhost:8757",
    "http://192.168.1.5:8757",
    "http://kiln.lan:8757",
    "not a url",
  ])("is false for %s", (origin) => {
    expect(is_default_address(origin)).toBe(false)
  })
})

describe("build_prompt", () => {
  it("is the base prompt on the default address", () => {
    expect(build_prompt(DEFAULT_ORIGIN)).toBe(BASE_PROMPT)
    expect(build_prompt("http://127.0.0.1:8757")).toBe(BASE_PROMPT)
  })

  it("names the real MCP server URL on another address", () => {
    expect(build_prompt("http://localhost:9000")).toBe(
      BASE_PROMPT + " The Kiln MCP server is at http://localhost:9000/mcp.",
    )
  })

  it("points at the install guide", () => {
    expect(
      BASE_PROMPT.startsWith(
        "Install Kiln's app, skill, and MCP following the guide here: ",
      ),
    ).toBe(true)
    expect(BASE_PROMPT.endsWith(AGENT_INSTALL_GUIDE_URL)).toBe(true)
  })
})

describe("app_origin", () => {
  it("is the API base URL under vite dev", () => {
    expect(app_origin(true)).toBe(base_url)
  })

  it("is the page origin in a build", () => {
    vi.stubGlobal("window", { location: { origin: "http://localhost:9000" } })
    expect(app_origin(false)).toBe("http://localhost:9000")
  })
})

describe("repo files that repeat the prompt and the stub skill", () => {
  it("README.md carries the same prompt in its coding agent section", () => {
    const lines = read_repo_file("README.md").split("\n")
    expect(lines).toContain(BASE_PROMPT)
    expect(lines).toContain("## Use Kiln from your coding agent")
  })

  it("agent_install.md holds the stub skill and the details an agent needs", () => {
    const guide = read_repo_file("agent_install.md")
    expect(guide).toContain(STUB_SKILL)
    expect(guide).toContain("http://localhost:8757/mcp")
    expect(guide).toContain("http://localhost:8757/ping")
    expect(guide).toContain("https://kiln.tech/download")
    const lines = guide.split("\n")
    for (const heading of [
      "### Claude Code",
      "### Codex",
      "### OpenCode",
      "### Any other agent",
    ]) {
      expect(lines).toContain(heading)
    }
  })

  it("agent_install.md stays short and does not name its own URL", () => {
    const guide = read_repo_file("agent_install.md")
    expect(guide.trimEnd().split("\n").length).toBeLessThanOrEqual(130)
    expect(guide).not.toContain(AGENT_INSTALL_GUIDE_URL)
  })
})
