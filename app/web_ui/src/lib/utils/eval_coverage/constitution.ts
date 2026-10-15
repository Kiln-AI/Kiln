/**
 * Reads the principles out of a task description.
 *
 * A constitution is markdown. Its principles are a numbered list under a
 * heading whose text contains "principle". When no such heading exists,
 * the longest numbered list in the text is used instead.
 */

export type Principle = {
  /** The number in the list, 1-based. */
  n: number
  text: string
}

const HEADING = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/
const ITEM = /^\s*(\d+)[.)]\s+(.*)$/

type Section = { heading: string; items: Principle[] }

function cleanText(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/\s+/g, " ")
    .trim()
}

function sections(description: string): Section[] {
  const out: Section[] = []
  let current: Section = { heading: "", items: [] }
  out.push(current)
  let lastItem: Principle | null = null
  for (const raw of description.split(/\r?\n/)) {
    const heading = raw.match(HEADING)
    if (heading) {
      current = { heading: heading[1], items: [] }
      out.push(current)
      lastItem = null
      continue
    }
    const item = raw.match(ITEM)
    if (item) {
      lastItem = { n: Number(item[1]), text: item[2] }
      current.items.push(lastItem)
      continue
    }
    if (lastItem && raw.trim() !== "" && /^\s+/.test(raw)) {
      lastItem.text += " " + raw.trim()
      continue
    }
    if (raw.trim() === "") {
      lastItem = null
    }
  }
  return out
}

export function parsePrinciples(
  description: string | null | undefined,
): Principle[] {
  if (!description) return []
  const all = sections(description)
  const named = all.find(
    (s) => /principle/i.test(s.heading) && s.items.length > 0,
  )
  const pick =
    named ??
    all
      .filter((s) => s.items.length >= 3)
      .sort((a, b) => b.items.length - a.items.length)[0]
  if (!pick) return []
  return pick.items.map((p, i) => ({
    n: Number.isFinite(p.n) && p.n > 0 ? p.n : i + 1,
    text: cleanText(p.text),
  }))
}
