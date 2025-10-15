import { describe, it, expect } from "vitest"

// Mock the sanitize_route_id function since it's inside a Svelte component
// We'll test the logic directly by extracting it
function sanitize_route_id(route_id: string | null | undefined) {
  if (!route_id) {
    return "/unknown"
  }
  // Strip components in round brackets like "(app)" from the route
  let sanitized = route_id.replace(/\/?\([^)]*\)/g, "")
  // Strip square brackets like "[id]" from the route
  sanitized = sanitized.replace(/\[([^\]]*)\]/g, "$1")
  // URL encode characters that aren't valid in URLs, but preserve slashes
  sanitized = sanitized
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/")
  // Ensure route always starts with a slash
  if (!sanitized.startsWith("/")) {
    sanitized = "/" + sanitized
  }
  return sanitized
}

describe("sanitize_route_id", () => {
  describe("unknown route handling", () => {
    it("should return /unknown for null input", () => {
      expect(sanitize_route_id(null)).toBe("/unknown")
    })

    it("should return /unknown for undefined input", () => {
      expect(sanitize_route_id(undefined)).toBe("/unknown")
    })

    it("should return /unknown for empty string", () => {
      expect(sanitize_route_id("")).toBe("/unknown")
    })
  })

  describe("bracket component stripping", () => {
    it("should strip single bracket component at start", () => {
      expect(sanitize_route_id("(app)/hello/world")).toBe("/hello/world")
    })

    it("should strip multiple bracket components", () => {
      expect(sanitize_route_id("(fullscreen)/(setup)/connect_providers")).toBe(
        "/connect_providers",
      )
    })

    it("should strip bracket components in middle of path", () => {
      expect(
        sanitize_route_id("/dataset/(project_id)/hello/(task_id)/world"),
      ).toBe("/dataset/hello/world")
    })

    it("should strip bracket components at end", () => {
      expect(sanitize_route_id("/hello/world/(component)")).toBe("/hello/world")
    })

    it("should handle nested bracket patterns", () => {
      expect(sanitize_route_id("(app)/(nested)/hello/(more)/world")).toBe(
        "/hello/world",
      )
    })

    it("should strip bracket with leading slash", () => {
      expect(sanitize_route_id("/(app)/hello")).toBe("/hello")
    })

    it("should strip bracket without leading slash", () => {
      expect(sanitize_route_id("(app)/hello")).toBe("/hello")
    })
  })

  describe("square bracket removal", () => {
    it("should remove single square bracket parameter", () => {
      expect(sanitize_route_id("finetune/[id]")).toBe("/finetune/id")
    })

    it("should remove multiple square bracket parameters", () => {
      expect(sanitize_route_id("project/[project_id]/task/[task_id]")).toBe(
        "/project/project_id/task/task_id",
      )
    })

    it("should remove square brackets at start", () => {
      expect(sanitize_route_id("[id]/hello")).toBe("/id/hello")
    })

    it("should remove square brackets at end", () => {
      expect(sanitize_route_id("/hello/[id]")).toBe("/hello/id")
    })

    it("should handle empty square brackets", () => {
      expect(sanitize_route_id("hello/[]/world")).toBe("/hello//world")
    })

    it("should handle square brackets with complex names", () => {
      expect(sanitize_route_id("evals/[eval_config_id]/[run_config_id]")).toBe(
        "/evals/eval_config_id/run_config_id",
      )
    })

    it("should handle mixed round and square brackets", () => {
      expect(sanitize_route_id("(app)/project/[project_id]/task")).toBe(
        "/project/project_id/task",
      )
    })
  })

  describe("URL encoding", () => {
    it("should encode spaces in route segments", () => {
      expect(sanitize_route_id("hello world/test")).toBe("/hello%20world/test")
    })

    it("should encode special characters", () => {
      expect(sanitize_route_id("hello@world/test#fragment")).toBe(
        "/hello%40world/test%23fragment",
      )
    })

    it("should encode unicode characters", () => {
      expect(sanitize_route_id("café/naïve")).toBe("/caf%C3%A9/na%C3%AFve")
    })

    it("should preserve slashes between segments", () => {
      expect(sanitize_route_id("hello/world/test")).toBe("/hello/world/test")
    })

    it("should handle multiple consecutive slashes", () => {
      expect(sanitize_route_id("hello//world///test")).toBe(
        "/hello//world///test",
      )
    })

    it("should encode query-like parameters", () => {
      expect(sanitize_route_id("search?q=hello world&type=all")).toBe(
        "/search%3Fq%3Dhello%20world%26type%3Dall",
      )
    })

    it("should encode parentheses and other special chars", () => {
      expect(sanitize_route_id("test(foo)/bar[baz]")).toBe("/test/barbaz")
    })

    it("should encode special chars that don't get removed", () => {
      expect(sanitize_route_id("test@email.com/price$100")).toBe(
        "/test%40email.com/price%24100",
      )
    })

    it("should handle combined encoding with bracket removal", () => {
      expect(sanitize_route_id("(app)/café/[user id]/naïve")).toBe(
        "/caf%C3%A9/user%20id/na%C3%AFve",
      )
    })
  })

  describe("slash normalization", () => {
    it("should add leading slash if missing", () => {
      expect(sanitize_route_id("hello/world")).toBe("/hello/world")
    })

    it("should preserve existing leading slash", () => {
      expect(sanitize_route_id("/hello/world")).toBe("/hello/world")
    })

    it("should handle root path", () => {
      expect(sanitize_route_id("/")).toBe("/")
    })

    it("should handle single word without slash", () => {
      expect(sanitize_route_id("hello")).toBe("/hello")
    })
  })

  describe("complex real-world scenarios", () => {
    it("should handle typical app route", () => {
      expect(sanitize_route_id("(app)/prompts/[project_id]/[task_id]")).toBe(
        "/prompts/project_id/task_id",
      )
    })

    it("should handle fullscreen setup route", () => {
      expect(
        sanitize_route_id("(fullscreen)/setup/(setup)/create_task/[slug]"),
      ).toBe("/setup/create_task/slug")
    })

    it("should handle nested dynamic routes", () => {
      expect(
        sanitize_route_id(
          "(app)/evals/[project_id]/[task_id]/[eval_id]/[eval_config_id]/[run_config_id]/run_result",
        ),
      ).toBe(
        "/evals/project_id/task_id/eval_id/eval_config_id/run_config_id/run_result",
      )
    })

    it("should handle route with only brackets", () => {
      expect(sanitize_route_id("(app)/(nested)")).toBe("/")
    })

    it("should handle mixed bracket and normal components", () => {
      expect(sanitize_route_id("settings/(project)/(task)/edit")).toBe(
        "/settings/edit",
      )
    })

    it("should handle consecutive slashes after bracket removal", () => {
      expect(sanitize_route_id("/hello/(bracket)//world")).toBe("/hello//world")
    })

    it("should handle route with only square brackets", () => {
      expect(sanitize_route_id("[id]/[slug]")).toBe("/id/slug")
    })

    it("should handle complex mixed scenario", () => {
      expect(
        sanitize_route_id(
          "(app)/dataset/[project_id]/(task)/[task_id]/run/[run_id]",
        ),
      ).toBe("/dataset/project_id/task_id/run/run_id")
    })
  })

  describe("edge cases", () => {
    it("should handle malformed brackets", () => {
      expect(sanitize_route_id("(unclosed/bracket")).toBe("/(unclosed/bracket")
    })

    it("should handle empty brackets", () => {
      expect(sanitize_route_id("()/hello/()")).toBe("/hello")
    })

    it("should handle brackets with special characters", () => {
      expect(sanitize_route_id("(app-test)/hello/(user_id)/world")).toBe(
        "/hello/world",
      )
    })

    it("should handle very long route", () => {
      const longRoute =
        "(app)/very/long/route/with/many/components/(bracket)/and/more/components"
      expect(sanitize_route_id(longRoute)).toBe(
        "/very/long/route/with/many/components/and/more/components",
      )
    })

    it("should handle route with only slashes", () => {
      expect(sanitize_route_id("///")).toBe("///")
    })

    it("should handle single character routes", () => {
      expect(sanitize_route_id("a")).toBe("/a")
    })

    it("should handle malformed square brackets", () => {
      expect(sanitize_route_id("[unclosed/bracket")).toBe(
        "/%5Bunclosed/bracket",
      )
    })

    it("should handle nested square brackets", () => {
      expect(sanitize_route_id("[outer[inner]]")).toBe("/outer%5Binner%5D")
    })

    it("should handle mixed malformed brackets", () => {
      expect(sanitize_route_id("(app]/[project)/task")).toBe("/task")
    })
  })
})
