import { describe, expect, it } from "vitest"
import { parsePrinciples } from "./constitution"

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
