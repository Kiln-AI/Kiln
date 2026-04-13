import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  isGitHubUrl,
  isGitLabUrl,
  gitHubPatDeepLink,
  gitLabPatDeepLink,
  gitHostname,
  gitOwnerFromUrl,
  gitRepoNameFromUrl,
  testAccess,
  listBranches,
  cloneRepo,
  renameClone,
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

describe("isGitLabUrl", () => {
  it("returns true for GitLab URLs", () => {
    expect(isGitLabUrl("https://gitlab.com/org/repo.git")).toBe(true)
    expect(isGitLabUrl("https://gitlab.example.com/org/repo.git")).toBe(true)
    expect(isGitLabUrl("git@gitlab.com:org/repo.git")).toBe(true)
  })

  it("returns false for non-GitLab URLs", () => {
    expect(isGitLabUrl("https://github.com/org/repo.git")).toBe(false)
    expect(isGitLabUrl("https://bitbucket.org/org/repo")).toBe(false)
    expect(isGitLabUrl("https://notgitlab.com/org/repo")).toBe(false)
    expect(isGitLabUrl("https://example.com/gitlab.backup/repo")).toBe(false)
  })
})

describe("gitHostname", () => {
  it("extracts hostname from HTTPS URLs", () => {
    expect(gitHostname("https://gitlab.com/org/repo.git")).toBe("gitlab.com")
    expect(gitHostname("https://gitlab.example.com/org/repo.git")).toBe(
      "gitlab.example.com",
    )
  })

  it("extracts hostname from SSH URLs", () => {
    expect(gitHostname("git@gitlab.com:org/repo.git")).toBe("gitlab.com")
    expect(gitHostname("git@gitlab.example.com:org/repo.git")).toBe(
      "gitlab.example.com",
    )
  })

  it("returns null for invalid URLs", () => {
    expect(gitHostname("not-a-url")).toBeNull()
  })
})

describe("gitOwnerFromUrl", () => {
  it("extracts owner from HTTPS GitHub URLs", () => {
    expect(gitOwnerFromUrl("https://github.com/Kiln-AI/sync_test")).toBe(
      "Kiln-AI",
    )
    expect(gitOwnerFromUrl("https://github.com/Kiln-AI/sync_test.git")).toBe(
      "Kiln-AI",
    )
  })

  it("extracts owner from HTTPS GitLab URLs", () => {
    expect(gitOwnerFromUrl("https://gitlab.com/my-org/repo.git")).toBe("my-org")
    expect(gitOwnerFromUrl("https://gitlab.example.com/my-org/repo.git")).toBe(
      "my-org",
    )
  })

  it("extracts owner from SSH URLs", () => {
    expect(gitOwnerFromUrl("git@github.com:Kiln-AI/repo.git")).toBe("Kiln-AI")
    expect(gitOwnerFromUrl("git@gitlab.com:my-org/repo.git")).toBe("my-org")
  })

  it("returns null for invalid URLs", () => {
    expect(gitOwnerFromUrl("not-a-url")).toBeNull()
  })

  it("handles owners with dots and dashes", () => {
    expect(gitOwnerFromUrl("https://github.com/my.org-name/repo.git")).toBe(
      "my.org-name",
    )
    expect(gitOwnerFromUrl("git@github.com:my.org-name/repo.git")).toBe(
      "my.org-name",
    )
  })

  it("returns null for URLs with no path segments", () => {
    expect(gitOwnerFromUrl("https://github.com")).toBeNull()
    expect(gitOwnerFromUrl("https://github.com/")).toBeNull()
  })
})

describe("gitRepoNameFromUrl", () => {
  it("extracts repo name from HTTPS URL", () => {
    expect(gitRepoNameFromUrl("https://github.com/Kiln-AI/kiln.git")).toBe(
      "kiln",
    )
  })

  it("extracts repo name from SSH URL", () => {
    expect(gitRepoNameFromUrl("git@github.com:Kiln-AI/kiln.git")).toBe("kiln")
  })

  it("handles URL without .git suffix", () => {
    expect(gitRepoNameFromUrl("https://github.com/Kiln-AI/kiln")).toBe("kiln")
  })

  it("handles repo names with dots and dashes", () => {
    expect(gitRepoNameFromUrl("https://github.com/owner/my-repo.v2.git")).toBe(
      "my-repo.v2",
    )
    expect(gitRepoNameFromUrl("https://github.com/owner/my-repo.v2")).toBe(
      "my-repo.v2",
    )
    expect(gitRepoNameFromUrl("git@github.com:owner/my-repo.v2.git")).toBe(
      "my-repo.v2",
    )
    expect(gitRepoNameFromUrl("git@github.com:owner/my-repo.v2")).toBe(
      "my-repo.v2",
    )
  })

  it("returns null for invalid URL", () => {
    expect(gitRepoNameFromUrl("not-a-url")).toBeNull()
  })
})

describe("gitHubPatDeepLink", () => {
  it("returns GitHub fine-grained token creation URL with repo name", () => {
    const link = gitHubPatDeepLink("https://github.com/Kiln-AI/kiln.git")
    expect(link).toContain("github.com/settings/personal-access-tokens/new")
    expect(link).toContain("contents=write")
    expect(link).toContain("Kiln%20AI%20for%20kiln")
    expect(link).toContain("auto%20sync%20for%20kiln")
  })

  it("falls back when repo name unavailable", () => {
    const link = gitHubPatDeepLink("")
    expect(link).toContain("name=Kiln%20AI")
    expect(link).not.toContain("for%20")
  })
})

describe("gitLabPatDeepLink", () => {
  it("returns GitLab token creation URL with correct scopes and repo name", () => {
    const link = gitLabPatDeepLink("https://gitlab.com/org/repo.git")
    expect(link).toContain("gitlab.com/-/user_settings/personal_access_tokens")
    expect(link).toContain("scopes=write_repository")
    expect(link).toContain("Kiln%20AI%20for%20repo")
  })

  it("uses self-hosted hostname", () => {
    const link = gitLabPatDeepLink("https://gitlab.example.com/org/repo.git")
    expect(link).toContain("gitlab.example.com/-/user_settings")
  })

  it("handles SSH URLs", () => {
    const link = gitLabPatDeepLink("git@gitlab.myco.com:org/repo.git")
    expect(link).toContain("gitlab.myco.com/-/user_settings")
  })

  it("falls back to gitlab.com for invalid URLs", () => {
    const link = gitLabPatDeepLink("not-a-url")
    expect(link).toContain("gitlab.com/-/user_settings")
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
    )
    expect(result.success).toBe(true)

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.git_url).toBe("https://github.com/org/repo.git")
    expect(body.branch).toBe("main")
    expect(body.pat_token).toBe("token")
    expect(body.auth_mode).toBe("pat_token")
  })
})

describe("renameClone", () => {
  it("sends correct request", async () => {
    const response = {
      new_clone_path: "/tmp/proj_123 - My Project",
      success: true,
      message: "OK",
    }
    mockFetch.mockResolvedValue(jsonResponse(response))

    const result = await renameClone("/tmp/clone_abc", "My Project", "proj_123")
    expect(result.success).toBe(true)
    expect(result.new_clone_path).toBe("/tmp/proj_123 - My Project")

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.clone_path).toBe("/tmp/clone_abc")
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
      project_path: "project.kiln",
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
