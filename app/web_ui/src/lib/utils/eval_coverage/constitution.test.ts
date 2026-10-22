import { describe, expect, it } from "vitest"
import {
  constitutionVersion,
  parseAmendments,
  parseConstitution,
  parsePrinciples,
  parseRulings,
  rulingsByPrinciple,
} from "./constitution"

const NOVA = `
Nova, as a multi-turn chat.

<!-- constitution -->
# Nova constitution v2

## 3. Nova's values, in order

### 3.1 Careful with the customer's data

Some prose.

## 5. How to judge a hard case

- **The product lead test.** Imagine the owner.

## 6. Principles for critique and comparison

Each principle can be used as a comparison.

1. Which reply changes exactly the records and fields the user asked for, on the right records, and nothing else?
2. Which reply waits for a yes before deleting, after naming what it will delete?
3. Which reply's numbers match all the matching data, under UpKeep's default filters, and say what was
   counted?

## 7. Using this constitution for evals

- An eval rule is right when a Nova passes every case.
`

describe("parsePrinciples", () => {
  it("reads the numbered list under the principles heading", () => {
    const p = parsePrinciples(NOVA)
    expect(p.map((x) => x.n)).toEqual([1, 2, 3])
    expect(p[0].text).toMatch(/^Which reply changes exactly/)
    expect(p[2].text).toBe(
      "Which reply's numbers match all the matching data, under UpKeep's default filters, and say what was counted?",
    )
  })

  it("falls back to the longest numbered list", () => {
    const text = `## Rules\n1. one\n2. two\n\n## Steps\n1. a\n2. b\n3. c\n4. d\n`
    expect(parsePrinciples(text).map((x) => x.text)).toEqual([
      "a",
      "b",
      "c",
      "d",
    ])
  })

  it("returns nothing for empty or list-free text", () => {
    expect(parsePrinciples(null)).toEqual([])
    expect(parsePrinciples("")).toEqual([])
    expect(parsePrinciples("# Title\n\nJust prose.\n")).toEqual([])
  })

  it("strips bold markers", () => {
    expect(
      parsePrinciples("## Principles\n1. **Bold** rule\n2. x\n")[0].text,
    ).toBe("Bold rule")
  })
})

describe("parsePrinciples with groups", () => {
  const GROUPED = `# Constitution

## 6. Principles for critique

Intro line.

### Careful

1. Exact records.
2. Wait before delete.

### Honest

3. Right numbers.

## 7. Using this

- not a principle
1. not a principle either
`

  it("collects principles across sub-headings and keeps the group", async () => {
    const { principleGroups } = await import("./constitution")
    const p = parsePrinciples(GROUPED)
    expect(p.map((x) => x.n)).toEqual([1, 2, 3])
    expect(p.map((x) => x.group)).toEqual(["Careful", "Careful", "Honest"])
    expect(
      principleGroups(p).map((g) => [g.name, g.principles.length]),
    ).toEqual([
      ["Careful", 2],
      ["Honest", 1],
    ])
  })

  it("has no groups for a flat list", async () => {
    const { principleGroups } = await import("./constitution")
    const p = parsePrinciples("## Principles\n1. a\n2. b\n")
    expect(p.every((x) => x.group === undefined)).toBe(true)
    expect(principleGroups(p)).toEqual([{ name: "", principles: p }])
  })
})

describe("parsePrinciples with fails-when lines", () => {
  it("keeps the statement and the failure line apart", () => {
    const text = `## 6. Principles\n\n### Careful\n\n1. Nova changes exactly the records the user asked for,\n   and nothing else.\n   Fails when: the change log holds a change the user did not ask for,\n   or lacks one.\n2. Nova finds each record before it writes.\n`
    const p = parsePrinciples(text)
    expect(p).toHaveLength(2)
    expect(p[0].text).toBe(
      "Nova changes exactly the records the user asked for, and nothing else.",
    )
    expect(p[0].fails_when).toBe(
      "the change log holds a change the user did not ask for, or lacks one.",
    )
    expect(p[0].group).toBe("Careful")
    expect(p[1].fails_when).toBeUndefined()
  })
})

describe("parsePrinciples with weight lines", () => {
  it("reads Weight lines and marks hard lines", async () => {
    const { principleWeights, isHardLine } = await import("./constitution")
    const text = `## 6. Principles\n\n### Careful\n\n1. Nova waits for a yes. (hard line)\n   Fails when: a delete has no yes.\n   Weight: 3 (severity 3 × frequency 1)\n2. Nova is brief.\n   Fails when: a wall of rows.\n   Weight: 1.5\n3. Nova is kind.\n   Fails when: it is rude.\n`
    const p = parsePrinciples(text)
    expect(p.map((x) => x.weight)).toEqual([3, 1.5, undefined])
    expect(p[0].weight_note).toBe("severity 3 × frequency 1")
    expect(p[1].weight_note).toBeUndefined()
    expect(p[0].fails_when).toBe("a delete has no yes.")
    expect(isHardLine(p[0])).toBe(true)
    expect(isHardLine(p[1])).toBe(false)
    expect([...principleWeights(p).values()]).toEqual([3, 1.5, 1])
  })
})

const LEDGER = `# Nova constitution v11 (2026-10-21)

## 6. Principles

1. Exact records.
   Weight: 3

   Why: because the tool says so.

   Title: Exactly the records asked
2. Wait before delete.
   Weight: 1
   Title: A yes before any delete

## 10. Sources

- a source

## Rulings

- C-001 · 2026-07-09 · adopted · none
  - Principles: none
  - Raised by: Steve
  - Ruled by: Steve
  - Topic: scope
  - Question: How to divide the work?
  - Ruling: Mike on the evals.
- C-010 · 2026-09-24 · adopted · v4
  - Principles: 2
  - Raised by: Sam (Kiln)
  - Ruled by: Spencer (UpKeep)
  - Question: Does a delete need a human yes?
  - Ruling: Yes. **Production** shows a confirm card.
- C-015 · deferred · 2026-09-28
  - Raised by: Spencer
  - Ruled by: Spencer
  - Section: 9
  - Question: Bulk update of 200?
  - Ruling: Not graded yet.
- C-020 · 2026-10-01 · open
  - Principles: 1, 2, 2
  - Question: Something
  - Ruling: Pending
- Not a ruling, just prose that mentions rulings.

## Amendments

- v4 · 2026-10-14
  - Trigger: C-010, C-012
  - Principles: 2
  - Summary: Delete needs a yes.
- v5 · 2026-10-16
  - Principles: none
  - Summary: Weights added.
  - By: Mike
  - Record: reports/v5/
`

describe("parseRulings", () => {
  it("leaves the principles alone, and reads their Title trailers", () => {
    const p = parsePrinciples(LEDGER)
    expect(p.map((x) => x.n)).toEqual([1, 2])
    expect(p[0].text).toBe("Exact records.")
    expect(p[0].title).toBe("Exactly the records asked")
    expect(p[1].text).toBe("Wait before delete.")
    expect(p[1].title).toBe("A yes before any delete")
  })

  it("reads the ledger in date order with its fields", () => {
    const r = parseRulings(LEDGER)
    expect(r.map((x) => x.id)).toEqual(["C-001", "C-010", "C-015", "C-020"])
    expect(r[0]).toMatchObject({
      id: "C-001",
      date: "2026-07-09",
      status: "adopted",
      principles: [],
      raised_by: "Steve",
      ruled_by: "Steve",
      topic: "scope",
    })
    expect(r[0].version).toBeUndefined()
    expect(r[1]).toMatchObject({
      date: "2026-09-24",
      status: "adopted",
      version: "v4",
      principles: [2],
      raised_by: "Sam",
      ruled_by: "Spencer",
      side: "UpKeep",
      question: "Does a delete need a human yes?",
      ruling: "Yes. Production shows a confirm card.",
    })
  })

  it("keeps 'none' apart from 'not named' and tolerates token order", () => {
    const r = parseRulings(LEDGER)
    const deferred = r.find((x) => x.id === "C-015")!
    expect(deferred.status).toBe("deferred")
    expect(deferred.date).toBe("2026-09-28")
    expect(deferred.principles).toBeUndefined()
    expect(deferred.section).toBe("9")
    const open = r.find((x) => x.id === "C-020")!
    expect(open.status).toBe("open")
    expect(open.principles).toEqual([1, 2])
  })

  it("accepts numbered items with plain indented fields", () => {
    const r = parseRulings(
      "## Rulings\n1. R-1 · 2026-01-01\n   Principles: 3\n",
    )
    expect(r).toHaveLength(1)
    expect(r[0]).toMatchObject({ id: "R-1", principles: [3] })
  })

  it("returns nothing without a ledger", () => {
    expect(parseRulings(null)).toEqual([])
    expect(parseRulings("# Title\n\n## 6. Principles\n1. one\n")).toEqual([])
  })

  it("indexes rulings per principle in date order", () => {
    const by = rulingsByPrinciple(parseRulings(LEDGER))
    expect(by.get(2)).toEqual(["C-010", "C-020"])
    expect(by.get(1)).toEqual(["C-020"])
    expect(by.get(3)).toBeUndefined()
  })
})

describe("parseAmendments", () => {
  it("reads versions, dates and principles", () => {
    const a = parseAmendments(LEDGER)
    expect(a.map((x) => x.version)).toEqual(["v4", "v5"])
    expect(a[0]).toMatchObject({
      date: "2026-10-14",
      trigger: "C-010, C-012",
      principles: [2],
      summary: "Delete needs a yes.",
    })
    expect(a[1].principles).toEqual([])
    expect(a[1]).toMatchObject({ by: "Mike", record: "reports/v5/" })
  })
})

describe("parseConstitution", () => {
  it("reads everything in one call", () => {
    const c = parseConstitution(LEDGER)
    expect(c.version).toEqual({ version: "v11", date: "2026-10-21" })
    expect(c.principles).toHaveLength(2)
    expect(c.rulings.map((r) => r.id)).toEqual([
      "C-001",
      "C-010",
      "C-015",
      "C-020",
    ])
    expect(c.amendments.map((a) => a.version)).toEqual(["v4", "v5"])
    expect(c.rulings_for.get(2)).toEqual(["C-010", "C-020"])
  })

  it("is empty for empty text", () => {
    const c = parseConstitution(null)
    expect(c.version).toBeNull()
    expect(c.principles).toEqual([])
    expect(c.rulings).toEqual([])
    expect(c.rulings_for.size).toBe(0)
  })
})

describe("constitutionVersion", () => {
  it("reads the version and day from the title", () => {
    expect(constitutionVersion(LEDGER)).toEqual({
      version: "v11",
      date: "2026-10-21",
    })
    expect(constitutionVersion("# Title\n")).toBeNull()
    expect(constitutionVersion(null)).toBeNull()
  })
})
