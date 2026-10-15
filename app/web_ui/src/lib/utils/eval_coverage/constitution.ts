/**
 * Reads the principles out of a task description.
 *
 * A constitution is markdown. Its principles are a numbered list under a
 * heading whose text contains "principle". Sub-headings inside that section
 * group the principles (for example by the value they serve); the group is
 * kept on each principle. When no such heading exists, the longest numbered
 * list in the text is used instead, with no groups.
 */

export type Principle = {
  /** The number in the list, 1-based. */
  n: number
  text: string
  /** The sub-heading the principle sits under, when the section has them. */
  group?: string
  /** The "Fails when: ..." line under the principle, when there is one. */
  fails_when?: string
}

const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/
const ITEM = /^\s*(\d+)[.)]\s+(.*)$/
const FAILS_WHEN = /^\s*fails when:\s*/i

type Section = { level: number; heading: string; items: Principle[] }

function cleanText(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/\s+/g, " ")
    .trim()
}

function sections(description: string): Section[] {
  const out: Section[] = []
  let current: Section = { level: 0, heading: "", items: [] }
  out.push(current)
  let lastItem: Principle | null = null
  for (const raw of description.split(/\r?\n/)) {
    const heading = raw.match(HEADING)
    if (heading) {
      current = { level: heading[1].length, heading: heading[2], items: [] }
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
      const line = raw.trim()
      if (FAILS_WHEN.test(line)) {
        lastItem.fails_when = line.replace(FAILS_WHEN, "")
      } else if (lastItem.fails_when !== undefined) {
        lastItem.fails_when += " " + line
      } else {
        lastItem.text += " " + line
      }
      continue
    }
    if (raw.trim() === "") {
      lastItem = null
    }
  }
  return out
}

function finish(items: Principle[]): Principle[] {
  return items.map((p, i) => ({
    ...p,
    n: Number.isFinite(p.n) && p.n > 0 ? p.n : i + 1,
    text: cleanText(p.text),
    ...(p.fails_when !== undefined
      ? { fails_when: cleanText(p.fails_when) }
      : {}),
  }))
}

export function parsePrinciples(
  description: string | null | undefined,
): Principle[] {
  if (!description) return []
  const all = sections(description)
  const start = all.findIndex((s) => /principle/i.test(s.heading))
  if (start >= 0) {
    const level = all[start].level
    const items: Principle[] = [...all[start].items]
    for (let i = start + 1; i < all.length; i++) {
      const s = all[i]
      if (s.level <= level) break
      for (const p of s.items) items.push({ ...p, group: cleanText(s.heading) })
    }
    if (items.length > 0) return finish(items)
  }
  const pick = all
    .filter((s) => s.items.length >= 3)
    .sort((a, b) => b.items.length - a.items.length)[0]
  if (!pick) return []
  return finish(pick.items)
}

/** The distinct groups in document order, with the principles of each. */
export function principleGroups(
  principles: Principle[],
): { name: string; principles: Principle[] }[] {
  const out: { name: string; principles: Principle[] }[] = []
  for (const p of principles) {
    const name = p.group ?? ""
    const last = out[out.length - 1]
    if (last && last.name === name) last.principles.push(p)
    else out.push({ name, principles: [p] })
  }
  return out
}
