import { describe, it, expect } from "vitest"
import { escapeHtml } from "./escape_html"

describe("escapeHtml", () => {
  it("turns a tag into text rather than markup", () => {
    expect(escapeHtml("<b>Boom</b>")).toBe("&lt;b&gt;Boom&lt;/b&gt;")
  })

  it("escapes the ampersand first, so an escape is not escaped twice", () => {
    expect(escapeHtml("Cost & Latency")).toBe("Cost &amp; Latency")
    expect(escapeHtml("&lt;")).toBe("&amp;lt;")
  })

  it("escapes a quote, which would otherwise close an attribute", () => {
    expect(escapeHtml('" onmouseover="alert(1)')).toBe(
      "&quot; onmouseover=&quot;alert(1)",
    )
  })

  it("escapes an apostrophe, which closes a single-quoted attribute", () => {
    expect(escapeHtml("' onmouseover='alert(1)")).toBe(
      "&#39; onmouseover=&#39;alert(1)",
    )
    expect(escapeHtml("Bob's Eval")).toBe("Bob&#39;s Eval")
  })
})
