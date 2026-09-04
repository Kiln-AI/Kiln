// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeAll, afterAll } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import ReviewField from "./review_field.svelte"
import { resolve_citation_span } from "./claim_evidence"
import { CITATION_SEGMENT_ATTR } from "./citation_highlight"

// jsdom has no scrollIntoView, which the field calls once a mark is placed.
const original_scroll_into_view = Element.prototype.scrollIntoView
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = function () {}
  }
})
afterAll(() => {
  Element.prototype.scrollIntoView = original_scroll_into_view
})
afterEach(() => {
  cleanup()
})

// A structured output at the size the bug was reported on: past 5000
// characters, one object with a repeated array of entries.
function jumbo_json_output(): string {
  const kinds = ["web_search", "news_outlet", "rss_feed", "twitter_query"]
  return JSON.stringify({
    summary:
      "Initial mention-source curation for Acme Construction Tech: seeded 15 probationary agent sources across web, news, RSS, X, and Reddit.",
    updated_mention_sources: Array.from({ length: 18 }, (_, i) => ({
      kind: kinds[i % kinds.length],
      value: `"Acme Construction Tech" source ${i} -site:acmeconstructiontech.example`,
      notes: `Seeded source ${i}: exact-name brand mentions scoped to the construction context and excluding the owned domain, so unrelated collisions stay out of the feed.`,
      addedBy: "agent",
      priority: "probationary",
    })),
  })
}

// What the trace modal hands a cited field: the anchors to find in the rendered
// body, plus the raw text and the span resolved against it to fall back to.
function cited_props(content: string, from: string, to: string) {
  const raw_span = resolve_citation_span(content, { from, to })
  expect(raw_span).not.toBeNull()
  return {
    content,
    tone: "output" as const,
    cited: { anchors: { from, to }, raw_text: content, raw_span: raw_span! },
  }
}

function marks(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll(`[${CITATION_SEGMENT_ATTR}]`))
}

function mark_text(container: HTMLElement): string {
  const found = marks(container)
  expect(found.length).toBeGreaterThan(0)
  return found.map((m) => m.textContent).join("")
}

describe("review_field — a cited JSON field", () => {
  it("marks inside the syntax-highlighted body, leaving it highlighted", () => {
    const raw = jumbo_json_output()
    // Pinned: the whole complaint is what a citation does to a LONG output.
    expect(raw.length).toBeGreaterThan(5000)
    const { container } = render(
      ReviewField,
      cited_props(raw, '{"summary":"Initial', "curation for Acme"),
    )

    // Same view as uncited: pretty-printed, syntax highlighted, whole.
    const body = container.querySelector("pre")!
    expect(body.textContent).toBe(JSON.stringify(JSON.parse(raw), null, 2))
    expect(container.querySelectorAll(".hljs-attr").length).toBeGreaterThan(0)
    // …with the cited range marked in place, colon-space and all.
    expect(mark_text(container)).toBe(
      '{\n  "summary": "Initial mention-source curation for Acme',
    )
  })

  it("segments a mark that crosses the highlighter's spans", () => {
    const { container } = render(
      ReviewField,
      cited_props(
        '{"window":"30 days","refund":"14 days"}',
        '"window":"30 days"',
        '"refund"',
      ),
    )

    // The range covers a key, its value and the next key: the highlighter put
    // each in its own element, so the mark arrives in pieces.
    expect(marks(container).length).toBeGreaterThan(1)
    expect(mark_text(container)).toBe('"window": "30 days",\n  "refund"')
    expect(container.querySelector(".hljs-attr")).not.toBeNull()
  })

  it("keeps the raw mark when the rendering genuinely lacks the anchors", async () => {
    // Re-serializing is not always byte-preserving: `1.50` comes back as
    // `1.5`, so an anchor written across that number is absent from the body on
    // screen. Losing the mark the reviewer clicked for would be worse than
    // showing it unformatted, so the raw text takes it.
    const raw = '{"price":1.50,"currency":"USD"}'
    const { container } = render(
      ReviewField,
      cited_props(raw, '"price":1.50', '"currency"'),
    )
    await tick()

    expect(container.querySelector("pre")).toBeNull()
    expect(container.textContent).toBe(raw)
    expect(container.querySelector("[data-citation-mark]")!.textContent).toBe(
      '"price":1.50,"currency"',
    )
  })
})

describe("review_field — a cited prose field", () => {
  it("marks through the markdown without unformatting it", () => {
    const prose = "Our **return window** is 30 days from purchase."
    const { container } = render(
      ReviewField,
      cited_props(prose, "return window", "30 days"),
    )

    // The formatting the reviewer was reading is still there…
    const bold = container.querySelector("strong")
    expect(bold).not.toBeNull()
    expect(bold!.textContent).toBe("return window")
    // …and the mark spans it, in pieces, because the bold is its own element.
    expect(mark_text(container)).toBe("return window is 30 days")
    expect(bold!.querySelector(`[${CITATION_SEGMENT_ATTR}]`)).not.toBeNull()
  })
})

describe("review_field — clearing the citation", () => {
  it("still re-renders its body after a citation has come and gone", async () => {
    // The marked range sits inside Svelte's {@html} block, whose insertion
    // point is an EMPTY text node. Re-joining the split halves with a blanket
    // normalize() deletes that anchor along with them; the body survives the
    // toggle and then renders blank — or throws — the next time its content
    // changes. Only a real component has those anchors, so only a real
    // component can catch it.
    const first = '{"window":"30 days"}'
    const second = '{"window":"14 days","refund":"7 days"}'
    const { container, rerender } = render(
      ReviewField,
      cited_props(first, '"window"', '"30 days"'),
    )
    expect(marks(container).length).toBeGreaterThan(0)

    await rerender({ cited: null })
    await rerender({ cited: null, content: second })

    expect(container.querySelector("pre")!.textContent).toBe(
      JSON.stringify(JSON.parse(second), null, 2),
    )
    expect(container.querySelector(".hljs-attr")).not.toBeNull()
  })

  it("leaves no mark behind and keeps the highlighted body", async () => {
    const raw = jumbo_json_output()
    const { container, rerender } = render(
      ReviewField,
      cited_props(raw, '{"summary":"Initial', "curation for Acme"),
    )
    expect(marks(container).length).toBeGreaterThan(0)

    await rerender({ cited: null })

    expect(marks(container)).toHaveLength(0)
    expect(container.querySelector("[data-citation-mark]")).toBeNull()
    expect(container.querySelector("mark")).toBeNull()
    // The body is untouched by the round trip: same text, still highlighted.
    expect(container.querySelector("pre")!.textContent).toBe(
      JSON.stringify(JSON.parse(raw), null, 2),
    )
    expect(container.querySelector(".hljs-attr")).not.toBeNull()
  })
})
