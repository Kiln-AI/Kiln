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
