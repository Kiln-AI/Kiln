import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  isGitHubUrl,
  gitHubPatDeepLink,
  testAccess,
  listBranches,
  cloneRepo,
  testWriteAccess,
  scanProjects,
  saveConfig,
  getConfig,
  updateConfig,
  deleteConfig,
} from "./api"

const mockFetch = vi.fn()
global.fetch = mockFetch

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: () => Promise.resolve(data),
  }
}

beforeEach(() => {
  mockFetch.mockReset()
})

describe("isGitHubUrl", () => {
  it("returns true for GitHub URLs", () => {
    expect(isGitHubUrl("https://github.com/org/repo.git")).toBe(true)
    expect(isGitHubUrl("https://github.com/org/repo")).toBe(true)
  })

  it("returns false for non-GitHub URLs", () => {
    expect(isGitHubUrl("https://gitlab.com/org/repo.git")).toBe(false)
    expect(isGitHubUrl("https://bitbucket.org/org/repo")).toBe(false)
  })
})

describe("gitHubPatDeepLink", () => {
  it("returns GitHub fine-grained token creation URL", () => {
    const link = gitHubPatDeepLink()
    expect(link).toContain("github.com/settings/personal-access-tokens/new")
    expect(link).toContain("contents=write")
    expect(link).toContain("Kiln")
  })
})

describe("testAccess", () => {
  it("sends correct request", async () => {
    const response = { success: true, message: "OK", auth_required: false }
    mockFetch.mockResolvedValue(jsonResponse(response))

    const result = await testAccess("https://github.com/org/repo.git", "token")
    expect(result).toEqual(response)
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/git_sync/test_access"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          git_url: "https://github.com/org/repo.git",
          pat_token: "token",
        }),
      }),
    )
  })

  it("sends null pat_token by default", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ success: true, message: "OK", auth_required: false }),
    )

    await testAccess("https://github.com/org/repo.git")
    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.pat_token).toBeNull()
  })
})

describe("listBranches", () => {
  it("returns branches and default", async () => {
    const response = { branches: ["main", "dev"], default_branch: "main" }
    mockFetch.mockResolvedValue(jsonResponse(response))

    const result = await listBranches("https://github.com/org/repo.git")
    expect(result.branches).toEqual(["main", "dev"])
    expect(result.default_branch).toBe("main")
  })
})

describe("cloneRepo", () => {
  it("sends all parameters", async () => {
    const response = {
      clone_path: "/tmp/clone",
      success: true,
      message: "OK",
    }
    mockFetch.mockResolvedValue(jsonResponse(response))

    const result = await cloneRepo(
      "https://github.com/org/repo.git",
      "main",
      "token",
      "pat_token",
      "My Project",
      "proj_123",
    )
    expect(result.success).toBe(true)

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.git_url).toBe("https://github.com/org/repo.git")
    expect(body.branch).toBe("main")
    expect(body.pat_token).toBe("token")
    expect(body.auth_mode).toBe("pat_token")
    expect(body.project_name).toBe("My Project")
    expect(body.project_id).toBe("proj_123")
  })
})

describe("testWriteAccess", () => {
  it("sends correct request", async () => {
    const response = {
      success: true,
      message: "OK",
      auth_required: false,
    }
    mockFetch.mockResolvedValue(jsonResponse(response))

    const result = await testWriteAccess("/tmp/clone", "token")
    expect(result.success).toBe(true)

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.clone_path).toBe("/tmp/clone")
    expect(body.pat_token).toBe("token")
  })
})

describe("scanProjects", () => {
  it("returns projects with id", async () => {
    const response = {
      projects: [
        {
          path: "project.kiln",
          name: "Test",
          description: "desc",
          id: "proj_abc",
        },
      ],
    }
    mockFetch.mockResolvedValue(jsonResponse(response))

    const result = await scanProjects("/tmp/clone")
    expect(result.projects).toHaveLength(1)
    expect(result.projects[0].id).toBe("proj_abc")
  })
})

describe("saveConfig", () => {
  it("sends config with all fields", async () => {
    const response = {
      sync_mode: "auto",
      remote_name: "origin",
      branch: "main",
      clone_path: "/tmp/clone",
      git_url: "https://github.com/org/repo.git",
      has_pat_token: true,
    }
    mockFetch.mockResolvedValue(jsonResponse(response))

    const result = await saveConfig({
      project_id: "proj_1",
      git_url: "https://github.com/org/repo.git",
      clone_path: "/tmp/clone",
      branch: "main",
      pat_token: "token",
    })
    expect(result.sync_mode).toBe("auto")
    expect(result.has_pat_token).toBe(true)
  })
})

describe("getConfig", () => {
  it("fetches config by project id", async () => {
    const response = {
      sync_mode: "auto",
      remote_name: "origin",
      branch: "main",
      clone_path: null,
      git_url: null,
      has_pat_token: false,
    }
    mockFetch.mockResolvedValue(jsonResponse(response))

    const result = await getConfig("proj_1")
    expect(result?.sync_mode).toBe("auto")
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/git_sync/config/proj_1"),
    )
  })
})

describe("updateConfig", () => {
  it("sends update request", async () => {
    const response = {
      sync_mode: "manual",
      remote_name: "origin",
      branch: "main",
      clone_path: null,
      git_url: null,
      has_pat_token: false,
    }
    mockFetch.mockResolvedValue(jsonResponse(response))

    const result = await updateConfig("proj_1", { sync_mode: "manual" })
    expect(result.sync_mode).toBe("manual")
  })
})

describe("deleteConfig", () => {
  it("sends DELETE request", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ message: "Config deleted" }))

    const result = await deleteConfig("proj_1")
    expect(result.message).toBe("Config deleted")
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/git_sync/config/proj_1"),
      expect.objectContaining({ method: "DELETE" }),
    )
  })

  it("throws on error response", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ detail: "Not found" }, 404))

    await expect(deleteConfig("nonexistent")).rejects.toThrow("Not found")
  })
})
