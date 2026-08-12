// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import ComparisonBasis, {
  basis_diagnostics,
  basis_line,
  basis_notes,
  small_set_warning,
  type BasisEval,
} from "./comparison_basis.svelte"
import {
  MIN_MATCHED_N,
  undetectable_difference_pp,
} from "$lib/utils/evolution/run_matching"

afterEach(cleanup)

function basis_eval(overrides: Partial<BasisEval> = {}): BasisEval {
  return {
    evalId: "e1",
    name: "Answer matches the data",
    matched: 25,
    shared: 25,
    universe_min: 25,
    universe_max: 74,
    ...overrides,
  }
}

describe("basis_line", () => {
  it("states the n range and the caveat at the default predicate", () => {
    const line = basis_line("all", "all", 3, [], { min: 11, max: 148 })
    expect(line).toBe(
      "All runs · n=11–148 by eval and config — configs are not compared on the same conversations",
    )
  })

  it("collapses a single n rather than printing 25–25", () => {
    expect(basis_line("all", "all", 2, [], { min: 25, max: 25 })).toContain(
      "n=25 by eval and config",
    )
  })

  it("says there is nothing to state when nothing is scored", () => {
    expect(basis_line("all", "all", 2, [], null)).toBe(
      "All runs · no scores yet on the pinned configs",
    )
  })

  it("explains a predicate that cannot apply to one config", () => {
    expect(basis_line("all", "shared", 1, [], { min: 5, max: 5 })).toBe(
      "All runs · Shared inputs needs at least 2 pinned configs",
    )
  })

  it("states matched against the universe it came out of", () => {
    const line = basis_line(
      "shared",
      "shared",
      3,
      [
        basis_eval({ matched: 22, universe_min: 25, universe_max: 74 }),
        basis_eval({ evalId: "e2", matched: 25, universe_min: 25 }),
      ],
      null,
    )
    expect(line).toBe(
      "Shared inputs · 3 configs · 22–25 matched conversations per eval (of 25–74)",
    )
  })

  it("names the shape source and its tolerance", () => {
    expect(
      basis_line("tools", "tools", 3, [basis_eval({ matched: 6 })], null),
    ).toContain("Shared inputs · similar tool use (within 1.5×)")
    expect(
      basis_line("length", "length", 2, [basis_eval({ matched: 15 })], null),
    ).toContain("similar length (within 1.5×)")
  })

  it("ignores evals nobody has run when quoting the range", () => {
    const line = basis_line(
      "shared",
      "shared",
      2,
      [
        basis_eval({ matched: 20, universe_min: 20, universe_max: 20 }),
        basis_eval({
          evalId: "never_run",
          matched: 0,
          universe_min: 0,
          universe_max: 0,
        }),
      ],
      null,
    )
    expect(line).toContain("20 matched conversations per eval (of 20)")
  })
})

describe("basis_notes", () => {
  it("attributes a cost gap to path divergence under All runs", () => {
    const notes = basis_notes("all")
    expect(notes).toHaveLength(1)
    expect(notes[0]).toContain("however differently they wandered")
  })

  it("attributes a cost move to the re-weighting whenever a predicate is on", () => {
    for (const predicate of ["shared", "length", "tools"] as const) {
      const notes = basis_notes(predicate)
      expect(
        notes.some((note) =>
          note.includes(
            "the usage rollup counts a conversation once per eval that scored it",
          ),
        ),
      ).toBe(true)
    }
  })

  it("says a cost gap under length matching is price per token", () => {
    const notes = basis_notes("length")
    expect(
      notes.some((note) =>
        note.includes("price per token rather than as work"),
      ),
    ).toBe(true)
    // ...and does NOT claim that under the other predicates
    expect(
      basis_notes("shared").some((note) => note.includes("price per token")),
    ).toBe(false)
  })

  it("calls the shape predicates lenses rather than controls", () => {
    for (const predicate of ["length", "tools"] as const) {
      expect(
        basis_notes(predicate).some((note) =>
          note.includes("a lens, not a control"),
        ),
      ).toBe(true)
    }
  })
})

describe("basis_diagnostics", () => {
  it("is silent at the default predicate, except about fetch failures", () => {
    expect(basis_diagnostics("all", [basis_eval()], ["X"], false, [])).toEqual(
      [],
    )
    const withError = basis_diagnostics("all", [], [], true, [
      { label: "Luna", message: "500" },
    ])
    expect(withError).toHaveLength(1)
    expect(withError[0]).toContain("Couldn't load runs for Luna: 500")
    expect(withError[0]).toContain("rather than pooled in")
  })

  it("names the evals with nothing matched", () => {
    const lines = basis_diagnostics(
      "shared",
      [
        basis_eval({ name: "Write Correctness", matched: 0 }),
        basis_eval({ evalId: "e2", name: "Answer matches", matched: 25 }),
      ],
      [],
      true,
      [],
    )
    expect(lines[0]).toBe(
      "No matched conversations on Write Correctness — that eval's cells are empty for this basis.",
    )
  })

  it("does not blame the predicate for an eval nobody has run", () => {
    const lines = basis_diagnostics(
      "shared",
      [basis_eval({ matched: 0, universe_min: 0, universe_max: 0 })],
      [],
      true,
      [],
    )
    expect(lines).toEqual([])
  })

  it("names the config that has no shape data, per predicate", () => {
    expect(
      basis_diagnostics(
        "tools",
        [basis_eval()],
        ["Motivated Stag"],
        true,
        [],
      )[0],
    ).toBe(
      "Motivated Stag has no tool-call metrics — Similar tool use is unavailable for this basis.",
    )
    expect(
      basis_diagnostics("length", [basis_eval()], ["A", "B"], true, [])[0],
    ).toBe(
      "A, B have no token counts — Similar length is unavailable for this basis.",
    )
  })

  it("says when the task itself records no tool calls", () => {
    const lines = basis_diagnostics("tools", [basis_eval()], ["A"], false, [])
    expect(lines).toEqual([
      "No eval on this task records tool calls, so Similar tool use has nothing to match on.",
    ])
  })
})

describe("small_set_warning", () => {
  it("never fires at the default predicate", () => {
    expect(small_set_warning("all", [basis_eval({ matched: 1 })])).toBeNull()
  })

  it("does not fire on a healthy matched set", () => {
    expect(
      small_set_warning("shared", [basis_eval({ matched: MIN_MATCHED_N })]),
    ).toBeNull()
  })

  it("quotes the resolution derived from the actual n", () => {
    const warning = small_set_warning("tools", [
      basis_eval({ name: "Writes one record at a time", matched: 7 }),
    ])
    const pp = undetectable_difference_pp(7)
    expect(warning?.text).toBe(
      `Small matched set: “Writes one record at a time” n=7 — differences under ~${pp}pp are undetectable here`,
    )
    expect(warning?.tooltip).toContain(
      "fitting to whichever runs the predicate",
    )
  })

  it("leads with the worst eval and counts the rest", () => {
    const warning = small_set_warning("shared", [
      basis_eval({ evalId: "a", name: "A", matched: 8 }),
      basis_eval({ evalId: "b", name: "B", matched: 3 }),
      basis_eval({ evalId: "c", name: "C", matched: 40 }),
    ])
    expect(warning?.text).toContain("“B” n=3")
    expect(warning?.text).toContain("(and 1 other eval)")
  })

  it("does not warn about an eval nobody has run", () => {
    expect(
      small_set_warning("shared", [
        basis_eval({ matched: 0, universe_min: 0, universe_max: 0 }),
      ]),
    ).toBeNull()
  })
})

describe("ComparisonBasis component", () => {
  it("renders the default-predicate line, its caveat, and no chip", () => {
    const { getByTestId, queryByTestId } = render(ComparisonBasis, {
      props: {
        applied: "all",
        requested: "all",
        basis_count: 3,
        evals: [],
        n_range: { min: 11, max: 148 },
      },
    })
    expect(getByTestId("basis-line").textContent).toContain(
      "not compared on the same conversations",
    )
    expect(queryByTestId("basis-warning")).toBeNull()
  })

  it("renders the weighting note and the small-set chip under a predicate", () => {
    const { getByTestId, getAllByTestId } = render(ComparisonBasis, {
      props: {
        applied: "tools",
        requested: "tools",
        basis_count: 3,
        evals: [basis_eval({ name: "Tiny", matched: 4 })],
        n_range: null,
      },
    })
    expect(getByTestId("basis-warning").textContent).toContain(
      "Small matched set",
    )
    const notes = getAllByTestId("basis-note").map((el) => el.textContent ?? "")
    expect(notes.some((note) => note.includes("each counted once"))).toBe(true)
  })

  it("says it is matching, and hides the stale line, while indexes load", () => {
    const { getByTestId, queryByTestId } = render(ComparisonBasis, {
      props: {
        applied: "all",
        requested: "shared",
        basis_count: 3,
        evals: [],
        n_range: { min: 11, max: 148 },
        loading: true,
      },
    })
    expect(getByTestId("basis-line").textContent?.trim()).toBe("Matching runs…")
    expect(queryByTestId("basis-note")).toBeNull()
    expect(queryByTestId("basis-warning")).toBeNull()
  })

  it("surfaces a fetch failure rather than pooling silently", () => {
    const { getAllByTestId } = render(ComparisonBasis, {
      props: {
        applied: "shared",
        requested: "shared",
        basis_count: 2,
        evals: [basis_eval()],
        n_range: null,
        errors: [{ label: "Luna", message: "Network error" }],
      },
    })
    const lines = getAllByTestId("basis-diagnostic").map(
      (el) => el.textContent ?? "",
    )
    expect(
      lines.some((line) => line.includes("Couldn't load runs for Luna")),
    ).toBe(true)
  })
})
