// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import {
  apply_citation_mark,
  clear_citation_marks,
  CITATION_MARK_ATTR,
  CITATION_SEGMENT_ATTR,
} from "./citation_highlight"

// A rendered body, written the way a syntax highlighter writes one: the text
// broken across elements that carry the colors.
function rendered(html: string): HTMLElement {
  const el = document.createElement("div")
  el.innerHTML = html
  return el
}

function segments(el: HTMLElement): HTMLElement[] {
  return Array.from(el.querySelectorAll(`[${CITATION_SEGMENT_ATTR}]`))
}

const HIGHLIGHTED =
  '<pre><span class="hljs-attr">"window"</span>: ' +
  '<span class="hljs-string">"30 days"</span>, ' +
  '<span class="hljs-attr">"refund"</span>: ' +
  '<span class="hljs-string">"14 days"</span></pre>'

describe("apply_citation_mark", () => {
  it("wraps a range that sits inside one element", () => {
    const el = rendered(HIGHLIGHTED)
    expect(apply_citation_mark(el, { from: "30 days", to: "30 days" })).toBe(
      true,
    )
    expect(segments(el)).toHaveLength(1)
    expect(segments(el)[0].textContent).toBe("30 days")
    // The color span the range sits in still owns it: the mark went INSIDE the
    // rendering rather than replacing it.
    expect(segments(el)[0].closest(".hljs-string")).not.toBeNull()
  })

  it("splits a range that crosses element boundaries into segments", () => {
    const el = rendered(HIGHLIGHTED)
    expect(apply_citation_mark(el, { from: '"window"', to: '"30 days"' })).toBe(
      true,
    )
    const marks = segments(el)
    // Key, the punctuation between, and value: three text nodes, three marks.
    expect(marks).toHaveLength(3)
    expect(marks.map((m) => m.textContent).join("")).toBe('"window": "30 days"')
    // Only the first is the scroll target, or a caller would be sent to
    // whichever segment the DOM happened to return first.
    expect(el.querySelectorAll(`[${CITATION_MARK_ATTR}]`)).toHaveLength(1)
    expect(marks[0].hasAttribute(CITATION_MARK_ATTR)).toBe(true)
    // Nothing was lost or duplicated in the rendering.
    expect(el.textContent).toBe(rendered(HIGHLIGHTED).textContent)
    expect(el.querySelectorAll(".hljs-attr")).toHaveLength(2)
  })

  it("resolves against the RENDERED text, not the source it came from", () => {
    // The anchors were retyped off a flush `"window":"30 days"`; the rendering
    // put a space after the colon and the highlighter split it in two.
    const el = rendered(HIGHLIGHTED)
    expect(
      apply_citation_mark(el, {
        from: '"window":"30 days"',
        to: '"window":"30 days"',
      }),
    ).toBe(true)
    expect(
      segments(el)
        .map((m) => m.textContent)
        .join(""),
    ).toBe('"window": "30 days"')
  })

  it("places nothing when the citation isn't in the rendering", () => {
    const el = rendered(HIGHLIGHTED)
    expect(apply_citation_mark(el, { from: '"restocking"', to: '"fee"' })).toBe(
      false,
    )
    expect(segments(el)).toHaveLength(0)
    expect(el.innerHTML).toBe(HIGHLIGHTED)
  })
})

describe("clear_citation_marks", () => {
  it("restores the DOM the renderer wrote", () => {
    const el = rendered(HIGHLIGHTED)
    apply_citation_mark(el, { from: '"window"', to: '"30 days"' })
    clear_citation_marks(el)
    // Byte-identical, not merely equivalent: leaving the split text nodes
    // behind would fragment the body a little more on every citation toggle.
    expect(el.innerHTML).toBe(HIGHLIGHTED)
    expect(el.querySelector("pre")!.childNodes).toHaveLength(
      rendered(HIGHLIGHTED).querySelector("pre")!.childNodes.length,
    )
  })

  it("keeps the empty text nodes a framework uses as anchors", () => {
    // Svelte marks its {#if} and {@html} insertion points with EMPTY text
    // nodes. A blanket normalize() to re-join the split halves would delete
    // every one of them, and the body would render blank the next time its
    // content changed. Only the halves this module split may be re-joined.
    const el = rendered("<pre></pre>")
    const pre = el.querySelector("pre")!
    pre.append(
      document.createTextNode("abc"),
      document.createTextNode(""),
      document.createTextNode("def"),
    )
    expect(apply_citation_mark(el, { from: "bc", to: "de" })).toBe(true)
    clear_citation_marks(el)

    const anchors = Array.from(pre.childNodes).filter(
      (n) => n.nodeType === n.TEXT_NODE && (n as Text).data === "",
    )
    expect(anchors).toHaveLength(1)
    // …and the halves it did split are back together, so a toggle does not
    // fragment the body a little further each time.
    expect(el.textContent).toBe("abcdef")
    expect(
      Array.from(pre.childNodes).filter(
        (n) => (n as Text).data && (n as Text).data.length > 0,
      ),
    ).toHaveLength(2)
  })

  it("leaves marks a surface rendered itself alone", () => {
    // The raw fallback writes its own <mark> through its markup. Unwrapping
    // that would delete a mark this module never placed.
    const el = rendered("<div>a <mark data-citation-mark>b</mark> c</div>")
    clear_citation_marks(el)
    expect(el.querySelector("mark")).not.toBeNull()
  })
})

describe("apply_citation_mark — repeated application", () => {
  it("converges on one set of marks instead of nesting them", () => {
    // The surfaces re-apply after every render, so this runs constantly.
    const el = rendered(HIGHLIGHTED)
    apply_citation_mark(el, { from: '"window"', to: '"30 days"' })
    const once = el.innerHTML
    apply_citation_mark(el, { from: '"window"', to: '"30 days"' })
    apply_citation_mark(el, { from: '"window"', to: '"30 days"' })
    expect(el.innerHTML).toBe(once)
    expect(el.querySelectorAll("mark mark")).toHaveLength(0)
  })

  it("moves the mark when the citation changes", () => {
    const el = rendered(HIGHLIGHTED)
    apply_citation_mark(el, { from: '"window"', to: '"30 days"' })
    apply_citation_mark(el, { from: '"refund"', to: '"14 days"' })
    expect(
      segments(el)
        .map((m) => m.textContent)
        .join(""),
    ).toBe('"refund": "14 days"')
    expect(el.textContent).toBe(rendered(HIGHLIGHTED).textContent)
  })
})
