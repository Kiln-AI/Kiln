// In-place citation marking — the reviewer keeps the view they were reading.
//
// A citation's anchors are written against the RAW text a judge saw, but the
// review surfaces render that text: JSON goes through the house Output idiom
// (pretty-printed and syntax highlighted), prose through the markdown renderer.
// Marking a character span in the raw string meant abandoning that rendering
// for the duration of the citation, which on a multi-thousand-character output
// dropped the reviewer into an unformatted blob.
//
// So the mark is applied to the DOM instead, find-in-page style: the surface
// renders exactly as it always does, and the cited range is then located in the
// RENDERED text and wrapped where it sits. The range routinely straddles
// element boundaries — a citation spanning a JSON key and its value crosses two
// syntax-highlight spans — so it becomes one mark per text node it covers.
//
// Resolution runs against the rendered text through the whitespace-tolerant
// fold, which is what absorbs the difference between the raw string and its
// rendering (`{"a":1}` read back as `{\n  "a": 1\n}`).

import {
  resolve_citation_span_whitespace_tolerant,
  type Citation,
} from "./claim_evidence"

// On the FIRST segment only: what a caller scrolls to, and the hook the
// surfaces have always used to find the mark.
export const CITATION_MARK_ATTR = "data-citation-mark"

// On every segment: what this module recognizes as its own to unwrap. Marks
// rendered by a surface's own markup (the raw fallback) do not carry it, so
// clearing never reaches into someone else's DOM.
export const CITATION_SEGMENT_ATTR = "data-citation-segment"

// No horizontal padding: a segmented mark would put a gap at every element
// boundary it crosses, mid-word, and the highlight is meant to read as one run.
const MARK_CLASS = "bg-warning/40 rounded"

// Which side of a segment was produced by splitting a text node, recorded when
// the split is made so clearing can put exactly those halves back together.
//
// The halves MUST be re-joined, or every citation toggle would fragment the
// body a little further. What must NOT happen is a blanket container.normalize()
// to do it: Svelte marks its {#if} and {@html} insertion points with EMPTY text
// nodes, and normalize() deletes every one of them in the container. The body
// survives the toggle and then renders blank the next time its content changes,
// because the anchor Svelte was going to insert at is gone. So the joins are
// tracked and applied one pair at a time instead.
const SPLIT_BEFORE_ATTR = "data-citation-split-before"
const SPLIT_AFTER_ATTR = "data-citation-split-after"

// Re-join a text node with the sibling it was split from. Empty siblings are
// never ours — splitText only ever produces non-empty halves here — and an
// empty text node next door is exactly the Svelte anchor this must not eat.
function join_split(node: Text, side: "before" | "after"): void {
  const sibling = side === "before" ? node.previousSibling : node.nextSibling
  if (!sibling || sibling.nodeType !== node.TEXT_NODE) return
  const other = sibling as Text
  if (other.data.length === 0) return
  if (side === "before") {
    other.appendData(node.data)
    node.remove()
  } else {
    node.appendData(other.data)
    other.remove()
  }
}

// Undo every mark this module placed, leaving the container's DOM as its
// renderer wrote it. Safe to call on a container that has none.
export function clear_citation_marks(container: HTMLElement): void {
  const marks = Array.from(
    container.querySelectorAll(`[${CITATION_SEGMENT_ATTR}]`),
  )
  for (const mark of marks) {
    const parent = mark.parentNode
    if (!parent) continue
    const split_before = mark.hasAttribute(SPLIT_BEFORE_ATTR)
    const split_after = mark.hasAttribute(SPLIT_AFTER_ATTR)
    const first = mark.firstChild
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark)
    parent.removeChild(mark)
    // The mark held exactly the one text node that was split out of the body,
    // so the joins are its own two edges.
    if (first && first.nodeType === first.TEXT_NODE) {
      if (split_after) join_split(first as Text, "after")
      if (split_before) join_split(first as Text, "before")
    }
  }
}

// One text node's slice of the container's rendered text.
type TextRun = { node: Text; start: number; end: number }

// The container's rendered text, with the node each character came from. This
// is the same walk the browser's own find-in-page does, and it is what makes
// the offsets line up with what is on screen rather than with the source.
function text_runs(container: HTMLElement): { text: string; runs: TextRun[] } {
  const walker = container.ownerDocument.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
  )
  const runs: TextRun[] = []
  let text = ""
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    const data = (node as Text).data
    if (!data) continue
    runs.push({
      node: node as Text,
      start: text.length,
      end: text.length + data.length,
    })
    text += data
  }
  return { text, runs }
}

// Find the citation in the container's rendered text and wrap it. Returns
// whether a mark was placed: false means the anchors are not in the rendering
// (a re-serialization the anchors predate, markdown syntax they were written
// across), and the caller falls back to marking the raw text rather than
// leaving the reviewer with no mark at all.
export function apply_citation_mark(
  container: HTMLElement,
  citation: Pick<Citation, "from" | "to">,
): boolean {
  // Always from a clean slate, so re-applying on every render cycle converges
  // on one set of marks instead of nesting them.
  clear_citation_marks(container)
  const { text, runs } = text_runs(container)
  const span = resolve_citation_span_whitespace_tolerant(text, citation)
  if (!span) return false
  let placed = 0
  for (const run of runs) {
    const start = Math.max(span.start, run.start)
    const end = Math.min(span.end, run.end)
    if (end <= start) continue
    if (!run.node.parentNode || !is_markable(run.node)) continue
    // Trim the node down to just the covered part: the tail after `start`, then
    // that node's own tail after the range ends. What is left IS the range.
    let node = run.node
    const split_before = start > run.start
    const split_after = end < run.end
    if (split_before) node = node.splitText(start - run.start)
    if (split_after) node.splitText(end - start)
    const mark = container.ownerDocument.createElement("mark")
    mark.setAttribute(CITATION_SEGMENT_ATTR, "")
    if (split_before) mark.setAttribute(SPLIT_BEFORE_ATTR, "")
    if (split_after) mark.setAttribute(SPLIT_AFTER_ATTR, "")
    if (placed === 0) mark.setAttribute(CITATION_MARK_ATTR, "")
    mark.className = MARK_CLASS
    node.parentNode?.replaceChild(mark, node)
    mark.appendChild(node)
    placed += 1
  }
  return placed > 0
}

// Elements whose children are structural, not text: the whitespace between two
// <li> is in the rendered text but has nowhere legal to put a <mark>, and the
// parser is entitled to move one that appears there. Such a node still COUNTS
// for offsets — it is part of what the reader sees — it just is not wrapped.
const STRUCTURAL_PARENTS = new Set([
  "UL",
  "OL",
  "DL",
  "TABLE",
  "THEAD",
  "TBODY",
  "TFOOT",
  "TR",
  "SELECT",
])

function is_markable(node: Text): boolean {
  const parent = node.parentElement
  if (!parent) return false
  return !(STRUCTURAL_PARENTS.has(parent.tagName) && !/\S/.test(node.data))
}

// Bring the mark into view. Called once per citation, not per render, so a
// reviewer scrolling away from a mark is not dragged back to it. That dedupe
// holds within ONE action instance: a remount starts a fresh one, so a surface
// that re-opens the cited row scrolls to the mark it just put back. Guarded
// because scrollIntoView is layout, which not every DOM implementation has —
// failing to scroll is not a reason to lose the mark.
function scroll_to_citation_mark(container: HTMLElement): void {
  const mark = container.querySelector(`[${CITATION_MARK_ATTR}]`)
  if (mark && typeof mark.scrollIntoView === "function") {
    mark.scrollIntoView({ block: "center", behavior: "smooth" })
  }
}

export type CitationMarkParams = {
  // The citation to mark, or null while browsing — which clears.
  citation: Pick<Citation, "from" | "to"> | null
  // Anything whose change means the rendered body may have been replaced (the
  // content, the row that is open). The mark is DOM the renderer does not know
  // about, so it has to be re-applied whenever the renderer rewrites the body,
  // and this is what tells the action that happened. Doubles as the scroll
  // key: one scroll per citation per body, not one per render.
  body: string
  // Narrow the search to part of the node. The rows use it to mark inside the
  // ONE row the citation belongs to: a collapsed row renders a truncated
  // preview of its message, and an unscoped search would happily mark that
  // preview instead of the answer being cited. Null means the part isn't
  // rendered, which is not a placement.
  within?: (node: HTMLElement) => HTMLElement | null
  // Whether the mark went in. A surface uses it to fall back to marking the raw
  // text. Reported from the settled pass only (see below).
  on_result?: (placed: boolean) => void
}

// Keep a citation marked in an element's rendered body.
//
// An ACTION rather than an afterUpdate: this runs inside the compiled fragment,
// which is the same place the body it marks is written, so it cannot be skipped
// by a lifecycle scheduler. It applies twice — once synchronously, so the mark
// is on screen in the same frame the body is, and once on a microtask, after
// any child render that the synchronous pass raced. Both passes clear first, so
// running twice is the same as running once.
export function citation_mark(node: HTMLElement, params: CitationMarkParams) {
  let current = params
  // What has already been scrolled to, held as its PARTS. Joining them into one
  // key would need a separator, and every candidate separator is a character
  // some model-written anchor is entitled to contain.
  let scrolled: { from: string; to: string; body: string } | null = null
  let live = true
  const apply = (report: boolean) => {
    const p = current
    const target = p.within ? p.within(node) : node
    // Clearing needs a target too, so it is answered before the missing-target
    // case — and browsing (no citation) is never reported as a failed
    // placement, which would send a surface to its fallback for no reason.
    if (!p.citation) {
      if (target) clear_citation_marks(target)
      scrolled = null
      return
    }
    // The synchronous pass may land before the body is there; only the settled
    // pass gets to tell a surface its citation could not be placed.
    if (!target) {
      if (report) p.on_result?.(false)
      return
    }
    const placed = apply_citation_mark(target, p.citation)
    if (report) p.on_result?.(placed)
    const seen =
      !!scrolled &&
      scrolled.from === p.citation.from &&
      scrolled.to === p.citation.to &&
      scrolled.body === p.body
    if (placed && !seen) {
      scrolled = { from: p.citation.from, to: p.citation.to, body: p.body }
      scroll_to_citation_mark(target)
    }
  }
  const schedule = () => {
    apply(false)
    queueMicrotask(() => {
      // The element can be gone by the time this runs — a citation cleared, a
      // trace switched. Marking a detached body is wasted work, and reporting
      // its result would drive a surface that no longer has this node.
      if (live) apply(true)
    })
  }
  schedule()
  return {
    update(next: CitationMarkParams) {
      current = next
      schedule()
    },
    destroy() {
      live = false
    },
  }
}
