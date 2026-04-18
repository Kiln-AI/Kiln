import { describe, it, expect } from "vitest"
import {
  try_convert_ssh_to_https,
  build_url_with_query_param,
} from "./url_utils"

describe("try_convert_ssh_to_https", () => {
  it("converts SCP-style git@github.com URLs to HTTPS", () => {
    expect(try_convert_ssh_to_https("git@github.com:user/repo.git")).toBe(
      "https://github.com/user/repo.git",
    )
  })

  it("converts SCP-style git@gitlab.com URLs to HTTPS", () => {
    expect(try_convert_ssh_to_https("git@gitlab.com:org/project.git")).toBe(
      "https://gitlab.com/org/project.git",
    )
  })

  it("converts ssh:// protocol URLs to HTTPS", () => {
    expect(try_convert_ssh_to_https("ssh://git@gitlab.com/user/repo.git")).toBe(
      "https://gitlab.com/user/repo.git",
    )
  })

  it("converts ssh:// protocol with nested paths", () => {
    expect(
      try_convert_ssh_to_https("ssh://git@github.com/org/sub/repo.git"),
    ).toBe("https://github.com/org/sub/repo.git")
  })

  it("leaves plain HTTPS URLs unchanged", () => {
    expect(try_convert_ssh_to_https("https://github.com/user/repo.git")).toBe(
      "https://github.com/user/repo.git",
    )
  })

  it("trims whitespace from URLs", () => {
    expect(
      try_convert_ssh_to_https("  https://github.com/user/repo.git  "),
    ).toBe("https://github.com/user/repo.git")
  })

  it("does not convert non-git user SCP-style URLs", () => {
    expect(try_convert_ssh_to_https("user@host.com:path/repo.git")).toBe(
      "user@host.com:path/repo.git",
    )
  })

  it("does not convert email-like strings", () => {
    expect(try_convert_ssh_to_https("user@example.com")).toBe(
      "user@example.com",
    )
  })

  it("does not convert ssh:// with non-git user", () => {
    expect(
      try_convert_ssh_to_https("ssh://admin@github.com/user/repo.git"),
    ).toBe("ssh://admin@github.com/user/repo.git")
  })
})

describe("build_url_with_query_param", () => {
  it("adds a query param to a URL without existing params", () => {
    const result = build_url_with_query_param(
      "http://localhost:3000/settings/import#git",
      "url",
      "https://github.com/org/repo.git",
    )
    expect(result).toBe(
      "http://localhost:3000/settings/import?url=https%3A%2F%2Fgithub.com%2Forg%2Frepo.git#git",
    )
  })

  it("updates an existing query param", () => {
    const result = build_url_with_query_param(
      "http://localhost:3000/settings/import?url=old-value#git",
      "url",
      "https://github.com/org/new-repo.git",
    )
    expect(result).toBe(
      "http://localhost:3000/settings/import?url=https%3A%2F%2Fgithub.com%2Forg%2Fnew-repo.git#git",
    )
  })

  it("removes the query param when value is null", () => {
    const result = build_url_with_query_param(
      "http://localhost:3000/settings/import?url=some-value#git",
      "url",
      null,
    )
    expect(result).toBe("http://localhost:3000/settings/import#git")
  })

  it("removes the query param when value is empty string", () => {
    const result = build_url_with_query_param(
      "http://localhost:3000/settings/import?url=some-value#git",
      "url",
      "",
    )
    expect(result).toBe("http://localhost:3000/settings/import#git")
  })

  it("preserves the hash fragment", () => {
    const result = build_url_with_query_param(
      "http://localhost:3000/page#section",
      "key",
      "value",
    )
    expect(result).toBe("http://localhost:3000/page?key=value#section")
  })

  it("preserves other query params", () => {
    const result = build_url_with_query_param(
      "http://localhost:3000/page?other=keep#hash",
      "url",
      "test",
    )
    expect(result).toBe("http://localhost:3000/page?other=keep&url=test#hash")
  })
})
