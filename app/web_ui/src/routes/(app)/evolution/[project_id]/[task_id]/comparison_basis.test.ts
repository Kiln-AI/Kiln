// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import ComparisonBasis, {
  basis_diagnostics,
  basis_line,
  basis_notes,
  small_set_warning,
  unavailable_lens_lines,
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
    universe: 25,
    shape_matched: null,
    missing_shape: 0,
    is_metric: false,
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

  it("explains a SHAPE predicate that cannot apply to one config", () => {
    expect(basis_line("all", "tools", 1, [], { min: 5, max: 5 })).toBe(
      "All runs · n=5 by eval and config — Similar tool use needs at least 2 pinned configs",
    )
  })

  it("does not nag about the default predicate on a single config", () => {
    // `shared` arriving here is not a choice anybody made - it is the default,
    // and matching is the identity on one config. Saying it "needs 2 configs"
    // would report a failure the reader never asked for.
    expect(basis_line("all", "shared", 1, [], { min: 5, max: 5 })).toBe(
      "All runs · n=5 by eval and config",
    )
  })

  it("states retention per eval, out of that eval's own universe", () => {
    // Never a range against a range: "22–25 (of 25–74)" pairs the smallest
    // matched count on one eval with the largest universe on another, and 22
    // of 74 describes no eval that exists.
    const line = basis_line(
      "shared",
      "shared",
      3,
      [
        basis_eval({ matched: 22, shared: 22, universe: 74 }),
        basis_eval({ evalId: "e2", matched: 25, shared: 25, universe: 25 }),
      ],
      null,
    )
    expect(line).toBe(
      "Shared inputs · 3 configs · kept 47/99 across 2 graded evals (22/74 · 25/25)",
    )
  })

  it("names the one eval rather than counting to one", () => {
    const line = basis_line(
      "shared",
      "shared",
      2,
      [basis_eval({ name: "Write Correctness", matched: 17, universe: 25 })],
      null,
    )
    expect(line).toBe(
      "Shared inputs · 2 configs · 17/25 conversations on “Write Correctness”",
    )
  })

  it("summarises the spread once there are more evals than fit", () => {
    const line = basis_line(
      "shared",
      "shared",
      6,
      [
        basis_eval({ evalId: "a", matched: 14, universe: 25 }),
        basis_eval({ evalId: "b", matched: 23, universe: 25 }),
        basis_eval({ evalId: "c", matched: 5, universe: 25 }),
        basis_eval({ evalId: "d", matched: 25, universe: 25 }),
      ],
      null,
    )
    expect(line).toContain(
      "kept 67/100 across 4 graded evals (5/25 to 25/25 each)",
    )
  })

  it("keeps the measurement lane out of the graded fraction", () => {
    // The metrics eval scores every conversation on the task; pooling its 175
    // items with the graded evals' 25 states a denominator that belongs to
    // neither.
    const line = basis_line(
      "shared",
      "shared",
      6,
      [
        basis_eval({ matched: 14, universe: 25 }),
        basis_eval({
          evalId: "eff",
          name: "Efficiency metrics",
          matched: 114,
          universe: 175,
          is_metric: true,
        }),
      ],
      null,
    )
    expect(line).toBe(
      "Shared inputs · 6 configs · 14/25 conversations on “Answer matches the data” · Efficiency metrics: 114/175",
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

  it("ignores evals nobody has run when quoting retention", () => {
    const line = basis_line(
      "shared",
      "shared",
      2,
      [
        basis_eval({ matched: 20, shared: 20, universe: 20 }),
        basis_eval({
          evalId: "never_run",
          matched: 0,
          shared: 0,
          universe: 0,
        }),
      ],
      null,
    )
    expect(line).toContain("20/20 conversations")
  })

  it("says so when there is nothing to match on at all", () => {
    expect(basis_line("shared", "shared", 2, [], null)).toBe(
      "Shared inputs · 2 configs · no runs to match on",
    )
  })
})

describe("unavailable_lens_lines", () => {
  const thin = [
    basis_eval({
      evalId: "a",
      name: "A",
      matched: 23,
      shared: 23,
      shape_matched: 6,
    }),
    basis_eval({
      evalId: "b",
      name: "B",
      matched: 25,
      shared: 25,
      shape_matched: 0,
    }),
    basis_eval({
      evalId: "c",
      name: "C",
      matched: 14,
      shared: 14,
      shape_matched: 0,
    }),
    basis_eval({
      evalId: "eff",
      name: "Efficiency",
      matched: 114,
      shared: 114,
      shape_matched: 100,
      is_metric: true,
    }),
  ]

  it("says nothing when the predicate applied", () => {
    expect(unavailable_lens_lines(null, "tools", 6, thin, [])).toEqual([])
    expect(
      unavailable_lens_lines("single_config", "tools", 1, thin, []),
    ).toEqual([])
  })

  it("quotes the retention the predicate actually produced, over graded evals", () => {
    // 6 of 62 shared graded conversations = 10%. The metrics eval's 100/114
    // does not soften it.
    const lines = unavailable_lens_lines("shape_too_thin", "tools", 6, thin, [])
    expect(lines[0]).toBe(
      "Similar tool use is unavailable at this basis: across 6 mutually-matched configs it keeps about 10% of the shared conversations, and this lens is built for 2–3. Showing shared inputs instead.",
    )
  })

  it("offers the two measurable exits, the recovery first", () => {
    const lines = unavailable_lens_lines("shape_too_thin", "tools", 6, thin, [
      {
        name: "Skill read returns an error",
        config: "DeepSeek V4 Pro",
        from: 5,
        to: 12,
      },
      {
        name: "Tool call returned an error",
        config: "DeepSeek V4 Pro",
        from: 6,
        to: 14,
      },
      { name: "A third one that does not fit", config: "X", from: 7, to: 9 },
    ])
    expect(lines[1]).toBe(
      "Dropping DeepSeek V4 Pro takes “Skill read returns an error” from 5 to 12 matched conversations.",
    )
    expect(lines[2]).toContain("Tool call returned an error")
    expect(lines).toHaveLength(4)
    expect(lines[3]).toBe(
      "Or compare 2–3 configs, which is what these predicates hold up at.",
    )
  })

  it("still offers the basis-size exit when no single config is the reason", () => {
    const lines = unavailable_lens_lines(
      "shape_too_thin",
      "length",
      5,
      thin,
      [],
    )
    expect(lines).toHaveLength(2)
    expect(lines[1]).toContain("compare 2–3 configs")
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
    expect(
      basis_diagnostics("all", "all", [basis_eval()], ["X"], false, []),
    ).toEqual([])
    const withError = basis_diagnostics("all", "all", [], [], true, [
      { label: "Luna", message: "500" },
    ])
    expect(withError).toHaveLength(1)
    expect(withError[0]).toContain("Couldn't load runs for Luna: 500")
    expect(withError[0]).toContain("rather than pooled in")
  })

  it("names every eval with nothing matched, rather than counting them", () => {
    // These are the evals that used to hide behind "(and 5 other evals)" on
    // the small-set chip. An eval with no cells at all is a different fact
    // from one with few, and it is the more serious one.
    const lines = basis_diagnostics(
      "shared",
      "shared",
      [
        basis_eval({ name: "Write Correctness", matched: 0 }),
        basis_eval({ evalId: "e2", name: "Skill read", matched: 0 }),
        basis_eval({ evalId: "e3", name: "Answer matches", matched: 25 }),
      ],
      [],
      true,
      [],
    )
    expect(lines[0]).toBe(
      "No matched conversations at all on “Write Correctness”, “Skill read” — those evals' cells are empty for this basis.",
    )
  })

  it("does not blame the predicate for an eval nobody has run", () => {
    const lines = basis_diagnostics(
      "shared",
      "shared",
      [basis_eval({ matched: 0, shared: 0, universe: 0 })],
      [],
      true,
      [],
    )
    expect(lines).toEqual([])
  })

  it("says which eval lost its conversations to a missing shape record", () => {
    // The number the reader needs is per eval: "17 of 17" is the whole reason
    // Write Correctness went blank, and pooling it across evals would read as
    // bad luck spread thinly.
    const lines = basis_diagnostics(
      "shared",
      "tools",
      [
        basis_eval({
          name: "Write Correctness",
          matched: 0,
          shared: 17,
          missing_shape: 17,
        }),
      ],
      [],
      true,
      [],
    )
    expect(lines).toContain(
      "“Write Correctness”: 17 of 17 shared conversations lack a same-run tool-call record.",
    )
  })

  it("names the missing shape for length matching in its own terms", () => {
    const lines = basis_diagnostics(
      "shared",
      "length",
      [basis_eval({ matched: 20, shared: 25, missing_shape: 5 })],
      [],
      true,
      [],
    )
    expect(lines[0]).toContain(
      "5 of 25 shared conversations have no recorded token count",
    )
  })

  it("caps the per-eval list and counts the rest", () => {
    const lines = basis_diagnostics(
      "shared",
      "tools",
      ["a", "b", "c", "d", "e"].map((id, i) =>
        basis_eval({
          evalId: id,
          name: id.toUpperCase(),
          matched: 1,
          shared: 20,
          missing_shape: 20 - i,
        }),
      ),
      [],
      true,
      [],
    )
    expect(
      lines.filter((line) => line.includes("lack a same-run")),
    ).toHaveLength(3)
    expect(lines).toContain("2 other evals lost conversations the same way.")
  })

  it("names the config that has no shape data, per predicate", () => {
    expect(
      basis_diagnostics(
        "tools",
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
      basis_diagnostics(
        "length",
        "length",
        [basis_eval()],
        ["A", "B"],
        true,
        [],
      )[0],
    ).toBe(
      "A, B have no token counts — Similar length is unavailable for this basis.",
    )
  })

  it("still explains the shape data after falling back to shared", () => {
    // applied is `shared` but the reader asked for `tools`, and why they did
    // not get it is the whole point of these lines.
    const lines = basis_diagnostics(
      "shared",
      "tools",
      [basis_eval()],
      ["Motivated Stag"],
      true,
      [],
    )
    expect(lines[0]).toContain("has no tool-call metrics")
  })

  it("says when the task itself records no tool calls", () => {
    const lines = basis_diagnostics(
      "tools",
      "tools",
      [basis_eval()],
      ["A"],
      false,
      [],
    )
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

  it("leaves the empty evals to the diagnostics that name them", () => {
    // n=0 is not a small sample, it is no sample: a resolution figure on it
    // would be nonsense, and it used to be what pushed the genuinely small
    // eval out of the chip.
    const warning = small_set_warning("shared", [
      basis_eval({ evalId: "a", name: "A", matched: 0 }),
      basis_eval({ evalId: "b", name: "B", matched: 0 }),
      basis_eval({ evalId: "c", name: "C", matched: 4 }),
    ])
    expect(warning?.text).toContain("“C” n=4")
    expect(warning?.text).not.toContain("other eval")
  })

  it("does not warn about an eval nobody has run", () => {
    expect(
      small_set_warning("shared", [
        basis_eval({ matched: 0, shared: 0, universe: 0 }),
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

  it("leads with the unavailable-lens explanation when it fell back", () => {
    const { getAllByTestId } = render(ComparisonBasis, {
      props: {
        applied: "shared",
        requested: "tools",
        fallback: "shape_too_thin",
        basis_count: 6,
        evals: [basis_eval({ matched: 23, shared: 23, shape_matched: 2 })],
        n_range: null,
        recovery: [
          { name: "Skill read", config: "DeepSeek V4 Pro", from: 5, to: 12 },
        ],
      },
    })
    const lines = getAllByTestId("basis-diagnostic").map(
      (el) => el.textContent?.trim() ?? "",
    )
    expect(lines[0]).toContain("Similar tool use is unavailable at this basis")
    expect(lines[1]).toContain("Dropping DeepSeek V4 Pro")
    expect(lines.some((line) => line.includes("compare 2–3 configs"))).toBe(
      true,
    )
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
