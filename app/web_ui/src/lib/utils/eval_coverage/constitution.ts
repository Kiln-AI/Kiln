/**
 * Reads the principles out of a task description.
 *
 * A constitution is markdown. Its principles are a numbered list under a
 * heading whose text contains "principle". Sub-headings inside that section
 * group the principles (for example by the value they serve); the group is
 * kept on each principle. Two indented lines under a principle carry its
 * checkable form and its importance: "Fails when: ..." and "Weight: <n>".
 * When no such heading exists, the longest numbered list in the text is
 * used instead, with no groups.
 */

export type Principle = {
  /** The number in the list, 1-based. */
  n: number
  text: string
  /** The sub-heading the principle sits under, when the section has them. */
  group?: string
  /** The "Fails when: ..." line under the principle, when there is one. */
  fails_when?: string
  /** The "Weight: <n>" line under the principle, when there is one. */
  weight?: number
  /** What follows the number on the Weight line, e.g. "severity 2 × frequency 3". */
  weight_note?: string
}

const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/
const ITEM = /^\s*(\d+)[.)]\s+(.*)$/
const FAILS_WHEN = /^\s*fails when:\s*/i
const WEIGHT = /^\s*weight:\s*/i
const HARD_LINE = /\(hard line\)/i

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
      } else if (WEIGHT.test(line)) {
        const rest = line.replace(WEIGHT, "").trim()
        const m = rest.match(/^([0-9]+(?:\.[0-9]+)?)\s*(.*)$/)
        const value = m ? Number(m[1]) : NaN
        if (Number.isFinite(value) && value > 0) {
          lastItem.weight = value
          const note = (m?.[2] ?? "").replace(/^[\s(—–:-]+|[\s)]+$/g, "").trim()
          if (note) lastItem.weight_note = note
        }
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

/** Importance per principle number; 1 when the text gives no weight. */
export function principleWeights(principles: Principle[]): Map<number, number> {
  return new Map(principles.map((p) => [p.n, p.weight ?? 1]))
}

/** True when the statement is marked "(hard line)". */
export function isHardLine(p: Principle): boolean {
  return HARD_LINE.test(p.text)
}

// ---------------------------------------------------------------------------
// Rulings and amendments
//
// A constitution may carry the court's rulings and its amendments as two more
// lists, under headings whose text contains "ruling" or "amendment" (one
// heading may hold both; the Nova contract puts "## Rulings" and
// "## Amendments" after the numbered sections). Each item is one bullet
// with a header line, and its fields are nested bullets, one per line:
//
//   - C-010 · 2026-09-24 · adopted · v4
//     - Principles: 3
//     - Raised by: Sam (Kiln)
//     - Ruled by: Spencer (UpKeep)
//     - Question: Does a delete need a human yes?
//     - Ruling: Yes. Production shows a confirm card before a delete.
//
//   - v4 · 2026-10-14
//     - Trigger: C-010, C-012
//     - Principles: 3, 5, 16
//     - Summary: Delete needs a yes; requests kept apart from work orders.
//
// Numbered items work the same way; bullets are preferred so a long ledger
// is never mistaken for the principles list.
// After the id, the header's tokens may come in any order: an ISO day, a
// status word and a version ("v4", or "none"). A Date, Status or Version
// line overrides the header. Unknown keys are ignored. "Principles: none"
// marks a ruling on method; a missing Principles line means the principles
// were not named, and the two are kept apart. An item whose header is not
// an id like "C-010" or a version like "v4" is skipped, so prose lists under
// such a heading do no harm.

export const RULING_STATUSES = [
  "adopted",
  "rejected",
  "deferred",
  "superseded",
  "open",
] as const
export type RulingStatus = (typeof RULING_STATUSES)[number]

export type Ruling = {
  id: string
  /** ISO day, or "" when the item gives none. */
  date: string
  /** "adopted" unless the item says otherwise. */
  status: RulingStatus
  /** The amendment the ruling landed in, e.g. "v4", when named. */
  version?: string
  /** Principle numbers. [] = none, a ruling on method; undefined = not named. */
  principles?: number[]
  raised_by?: string
  ruled_by?: string
  /** The side of whoever ruled, from "Ruled by: Name (Side)" or a Side line. */
  side?: string
  question?: string
  ruling?: string
  topic?: string
  source?: string
  supersedes?: string
}

export type Amendment = {
  version: string
  date?: string
  trigger?: string
  summary?: string
  principles?: number[]
  supersedes?: string
}

const LEDGER_HEADING = /ruling|amendment/i
const LIST_ITEM = /^\s{0,1}(?:\d+[.)]|[-*•])\s+(.*)$/
const FIELD = /^\s*([A-Za-z][A-Za-z ]{0,30}?)\s*:\s*(.*)$/
const RULING_ID = /^[A-Za-z]{1,8}-\d{1,6}[a-z]?$/
const VERSION = /^v\d+$/i
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/
const SEPARATOR = /\s+[·|—–-]\s+|\s*,\s+/

type RawItem = { header: string; fields: Map<string, string> }

/** The list items under every heading that names rulings or amendments. */
function ledgerItems(description: string): RawItem[] {
  const out: RawItem[] = []
  let inside = false
  let level = 0
  let item: RawItem | null = null
  let lastKey: string | null = null
  for (const raw of description.split(/\r?\n/)) {
    const heading = raw.match(HEADING)
    if (heading) {
      const l = heading[1].length
      if (inside && l <= level) inside = false
      if (!inside && LEDGER_HEADING.test(heading[2])) {
        inside = true
        level = l
      }
      item = null
      lastKey = null
      continue
    }
    if (!inside) continue
    const li = raw.match(LIST_ITEM)
    if (li) {
      item = { header: li[1].trim(), fields: new Map() }
      out.push(item)
      lastKey = null
      continue
    }
    if (!item || raw.trim() === "" || !/^\s+/.test(raw)) continue
    // A field is a nested bullet ("  - Key: value"); a bare indented line is accepted too.
    const line = raw.replace(/^(\s+)[-*•]\s+/, "$1")
    const field = line.match(FIELD)
    if (field) {
      lastKey = field[1].trim().toLowerCase().replace(/\s+/g, " ")
      item.fields.set(lastKey, field[2].trim())
    } else if (lastKey) {
      // A wrapped field line: the contract asks for one line, but we forgive it.
      item.fields.set(lastKey, `${item.fields.get(lastKey)} ${line.trim()}`)
    }
  }
  return out
}

function headerTokens(header: string): string[] {
  return header
    .replace(/\*\*/g, "")
    .split(SEPARATOR)
    .map((t) => t.trim().replace(/[:;]$/, ""))
    .filter(Boolean)
}

/** "3, 5, 16" -> [3, 5, 16]; "none", "-" or "—" -> []; nothing usable -> undefined. */
function parseNumbers(value: string | undefined): number[] | undefined {
  if (value === undefined) return undefined
  const v = value.trim()
  if (v === "" || /^(none|no|n\/a|-|—|–)$/i.test(v)) return []
  const nums = Array.from(v.matchAll(/\d+/g), (m) => Number(m[0])).filter(
    (n) => Number.isFinite(n) && n > 0,
  )
  return Array.from(new Set(nums))
}

/** "Spencer (UpKeep)" -> { name: "Spencer", side: "UpKeep" }. */
function nameAndSide(value: string): { name: string; side?: string } {
  const m = value.match(/^(.*?)\s*\(([^)]+)\)\s*$/)
  if (!m) return { name: value.trim() }
  return { name: m[1].trim(), side: m[2].trim() }
}

function isStatus(token: string): token is RulingStatus {
  return (RULING_STATUSES as readonly string[]).includes(token.toLowerCase())
}

function rulingFrom(item: RawItem): Ruling | null {
  const tokens = headerTokens(item.header)
  const id = tokens[0] ?? ""
  if (!RULING_ID.test(id)) return null
  const r: Ruling = { id, date: "", status: "adopted" }
  for (const t of tokens.slice(1)) {
    if (ISO_DAY.test(t)) r.date = t
    else if (isStatus(t)) r.status = t.toLowerCase() as RulingStatus
    else if (VERSION.test(t)) r.version = t.toLowerCase()
  }
  const f = item.fields
  const date = f.get("date")
  if (date && ISO_DAY.test(date)) r.date = date
  const status = f.get("status")
  if (status && isStatus(status))
    r.status = status.toLowerCase() as RulingStatus
  const version = f.get("version")
  if (version && VERSION.test(version)) r.version = version.toLowerCase()
  else if (version && /^none$/i.test(version)) delete r.version
  const principles = parseNumbers(f.get("principles") ?? f.get("principle"))
  if (principles !== undefined) r.principles = principles
  const raised = f.get("raised by")
  if (raised) r.raised_by = nameAndSide(raised).name
  const ruled = f.get("ruled by")
  if (ruled) {
    const { name, side } = nameAndSide(ruled)
    r.ruled_by = name
    if (side) r.side = side
  }
  const side = f.get("side")
  if (side) r.side = side
  for (const key of [
    "question",
    "ruling",
    "topic",
    "source",
    "supersedes",
  ] as const) {
    const v = f.get(key)
    if (v) r[key] = cleanText(v)
  }
  return r
}

function amendmentFrom(item: RawItem): Amendment | null {
  const tokens = headerTokens(item.header)
  const version = tokens[0] ?? ""
  if (!VERSION.test(version)) return null
  const a: Amendment = { version: version.toLowerCase() }
  for (const t of tokens.slice(1)) if (ISO_DAY.test(t)) a.date = t
  const f = item.fields
  const date = f.get("date")
  if (date && ISO_DAY.test(date)) a.date = date
  const principles = parseNumbers(f.get("principles") ?? f.get("principle"))
  if (principles !== undefined) a.principles = principles
  for (const key of ["trigger", "summary", "supersedes"] as const) {
    const v = f.get(key)
    if (v) a[key] = cleanText(v)
  }
  return a
}

/** Rulings in date order (then id), earliest first. */
export function sortRulings(rulings: Ruling[]): Ruling[] {
  return [...rulings].sort(
    (a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id),
  )
}

/** The court's rulings in the task description, in date order. */
export function parseRulings(description: string | null | undefined): Ruling[] {
  if (!description) return []
  const out: Ruling[] = []
  const seen = new Set<string>()
  for (const item of ledgerItems(description)) {
    const r = rulingFrom(item)
    if (!r || seen.has(r.id)) continue
    seen.add(r.id)
    out.push(r)
  }
  return sortRulings(out)
}

/** The constitution's amendments in the task description, in document order. */
export function parseAmendments(
  description: string | null | undefined,
): Amendment[] {
  if (!description) return []
  const out: Amendment[] = []
  const seen = new Set<string>()
  for (const item of ledgerItems(description)) {
    const a = amendmentFrom(item)
    if (!a || seen.has(a.version)) continue
    seen.add(a.version)
    out.push(a)
  }
  return out
}

/** Ruling ids per principle number, in date order. */
export function rulingsByPrinciple(rulings: Ruling[]): Map<number, string[]> {
  const out = new Map<number, string[]>()
  for (const r of sortRulings(rulings)) {
    for (const n of r.principles ?? []) {
      const list = out.get(n)
      if (list) list.push(r.id)
      else out.set(n, [r.id])
    }
  }
  return out
}

/** The version and day in the constitution's title, e.g. "# Nova constitution v11 (2026-10-21)". */
export function constitutionVersion(
  description: string | null | undefined,
): { version: string; date?: string } | null {
  if (!description) return null
  for (const raw of description.split(/\r?\n/)) {
    const heading = raw.match(HEADING)
    if (!heading) continue
    const m = heading[2].match(/\bv(\d+)\b/i)
    if (!m) continue
    const date = heading[2].match(/\d{4}-\d{2}-\d{2}/)
    return { version: `v${m[1]}`, ...(date ? { date: date[0] } : {}) }
  }
  return null
}
