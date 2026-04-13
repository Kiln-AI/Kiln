import { describe, it, expect } from "vitest"
import {
  initialAuthFormMode,
  buildOAuthUpdatePayload,
  buildPatUpdatePayload,
} from "./auth_form_mode"

describe("initialAuthFormMode", () => {
  it("returns oauth for GitHub URL with github_oauth auth mode", () => {
    expect(
      initialAuthFormMode("github_oauth", "https://github.com/org/repo.git"),
    ).toBe("oauth")
  })

  it("returns pat for GitHub URL with pat_token auth mode", () => {
    expect(
      initialAuthFormMode("pat_token", "https://github.com/org/repo.git"),
    ).toBe("pat")
  })

  it("returns pat for GitHub URL with system_keys auth mode", () => {
    expect(
      initialAuthFormMode("system_keys", "https://github.com/org/repo.git"),
    ).toBe("pat")
  })

  it("returns pat for GitLab URL regardless of auth mode", () => {
    expect(
      initialAuthFormMode("pat_token", "https://gitlab.com/org/repo.git"),
    ).toBe("pat")
    expect(
      initialAuthFormMode("github_oauth", "https://gitlab.com/org/repo.git"),
    ).toBe("pat")
  })

  it("returns pat when git_url is null or empty", () => {
    expect(initialAuthFormMode("github_oauth", null)).toBe("pat")
    expect(initialAuthFormMode("github_oauth", "")).toBe("pat")
    expect(initialAuthFormMode(undefined, undefined)).toBe("pat")
  })
})

describe("buildOAuthUpdatePayload", () => {
  it("includes oauth_token and auth_mode github_oauth", () => {
    expect(buildOAuthUpdatePayload("ghu_abc123")).toEqual({
      oauth_token: "ghu_abc123",
      auth_mode: "github_oauth",
    })
  })
})

describe("buildPatUpdatePayload", () => {
  it("includes auth_mode switch when current mode is github_oauth", () => {
    expect(buildPatUpdatePayload("ghp_token", "github_oauth")).toEqual({
      pat_token: "ghp_token",
      auth_mode: "pat_token",
    })
  })

  it("includes auth_mode switch when current mode is system_keys", () => {
    expect(buildPatUpdatePayload("ghp_token", "system_keys")).toEqual({
      pat_token: "ghp_token",
      auth_mode: "pat_token",
    })
  })

  it("omits auth_mode when already on pat_token", () => {
    expect(buildPatUpdatePayload("ghp_token", "pat_token")).toEqual({
      pat_token: "ghp_token",
    })
  })

  it("includes auth_mode when current mode is null or undefined", () => {
    expect(buildPatUpdatePayload("ghp_token", null)).toEqual({
      pat_token: "ghp_token",
      auth_mode: "pat_token",
    })
    expect(buildPatUpdatePayload("ghp_token", undefined)).toEqual({
      pat_token: "ghp_token",
      auth_mode: "pat_token",
    })
  })
})
