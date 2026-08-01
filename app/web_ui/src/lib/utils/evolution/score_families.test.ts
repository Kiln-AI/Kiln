import { describe, it, expect } from "vitest"
import type { components } from "$lib/api_schema"
import {
  build_score_families,
  family_for_eval,
  family_from_tags,
  family_label,
  family_rank,
  order_families,
  OTHER_FAMILY_ID,
} from "./score_families"

type Spec = components["schemas"]["Spec"]

function spec(
  overrides: {
    id?: string
    eval_id?: string | null
    tags?: string[]
    spec_type?: string
  } = {},
): Spec {
  return {
    v: 1,
    id: overrides.id ?? "spec",
    name: overrides.id ?? "spec",
    definition: "",
    // The properties union is discriminated on spec_type; only that field is
    // read here, so the rest of an issue's shape is not worth building out.
    properties: {
      spec_type: overrides.spec_type ?? "issue",
    } as Spec["properties"],
    priority: 1,
    status: "active",
    tags: overrides.tags ?? [],
    eval_id: overrides.eval_id === undefined ? "eval" : overrides.eval_id,
  } as Spec
}

describe("family_from_tags", () => {
  it("reads the family out of a fam_ tag", () => {
    expect(family_from_tags(["lane_det", "fam_data_integrity"])).toBe(
      "data_integrity",
    )
  })

  it("accepts the separators and prefixes teams actually use", () => {
    expect(family_from_tags(["family:tool-routing"])).toBe("tool-routing")
    expect(family_from_tags(["FAM-Reliability"])).toBe("reliability")
    expect(family_from_tags(["family_workflow"])).toBe("workflow")
  })

  it("ignores tags that only look like one", () => {
    expect(family_from_tags(["family", "fam", "familiar_thing"])).toBe(null)
    expect(family_from_tags(["fam_"])).toBe(null)
    expect(family_from_tags([])).toBe(null)
    expect(family_from_tags(null)).toBe(null)
  })
})

describe("family_label", () => {
  it("turns an id into a heading", () => {
    expect(family_label("data_integrity")).toBe("Data Integrity")
    expect(family_label("workflow")).toBe("Workflow")
    expect(family_label("tool-routing")).toBe("Tool Routing")
  })

  it("leaves an acronym the task capitalized alone", () => {
    expect(family_label("PII")).toBe("PII")
    expect(family_label("PII_leaks")).toBe("PII Leaks")
  })
})

describe("build_score_families", () => {
  it("prefers the family the specs declare over their type", () => {
    // Every spec is an `issue`, which is exactly Nova's shape: the built-in
    // taxonomy says nothing, and the tags say everything.
    const families = build_score_families([
      spec({ eval_id: "a", tags: ["fam_structural"] }),
      spec({ eval_id: "b", tags: ["fam_structural"] }),
      spec({ eval_id: "c", tags: ["fam_format"] }),
      spec({ eval_id: "d", tags: ["fam_workflow"] }),
    ])
    expect(families.get("a")?.label).toBe("Structural")
    expect(families.get("c")?.label).toBe("Format")
    expect(new Set([...families.values()].map((f) => f.id)).size).toBe(3)
  })

  it("falls back to spec_type when nothing declares a family", () => {
    const families = build_score_families([
      spec({ eval_id: "a", spec_type: "toxicity" }),
      spec({ eval_id: "b", spec_type: "localization" }),
      spec({ eval_id: "c", spec_type: "localization" }),
    ])
    expect(families.get("a")?.label).toBe("Toxicity")
    expect(families.get("b")?.label).toBe("Localization")
  })

  it("groups nothing when the task declares no usable taxonomy", () => {
    // One spec_type across the board is not a grouping - it is one bucket
    expect(
      build_score_families([
        spec({ eval_id: "a", spec_type: "issue" }),
        spec({ eval_id: "b", spec_type: "issue" }),
      ]).size,
    ).toBe(0)
    expect(build_score_families([]).size).toBe(0)
    expect(build_score_families(null).size).toBe(0)
  })

  it("ignores a tagging scheme only a corner of the task opted into", () => {
    // Two specs out of ten would file the other eight under "Other" and call
    // it a taxonomy. spec_type is uniform here, so nothing groups at all.
    const specs = [
      spec({ eval_id: "a", tags: ["fam_format"] }),
      spec({ eval_id: "b", tags: ["fam_workflow"] }),
      ...Array.from({ length: 8 }, (_, index) =>
        spec({ eval_id: `n${index}` }),
      ),
    ]
    expect(build_score_families(specs).size).toBe(0)
  })

  it("takes spec_type when the tags are too sparse but types are not", () => {
    const specs = [
      spec({ eval_id: "a", tags: ["fam_format"], spec_type: "formatting" }),
      spec({ eval_id: "b", spec_type: "toxicity" }),
      spec({ eval_id: "c", spec_type: "toxicity" }),
      spec({ eval_id: "d", spec_type: "bias" }),
    ]
    const families = build_score_families(specs)
    // The fam_ tag covered 1 of 4, so the built-in taxonomy wins outright
    expect(families.get("a")?.label).toBe("Formatting")
    expect(families.get("b")?.label).toBe("Toxicity")
  })

  it("skips specs with no eval, which have no score to group", () => {
    const families = build_score_families([
      spec({ eval_id: null, tags: ["fam_future"] }),
      spec({ eval_id: "a", tags: ["fam_format"] }),
      spec({ eval_id: "b", tags: ["fam_workflow"] }),
    ])
    expect(families.size).toBe(2)
    // ...and an unarmed spec does not count against coverage either
    expect(families.get("a")?.id).toBe("format")
  })
})

describe("family_for_eval", () => {
  it("files an eval the scheme missed under Other", () => {
    const families = build_score_families([
      spec({ eval_id: "a", tags: ["fam_format"] }),
      spec({ eval_id: "b", tags: ["fam_workflow"] }),
    ])
    expect(family_for_eval(families, "a").id).toBe("format")
    expect(family_for_eval(families, "unknown").id).toBe(OTHER_FAMILY_ID)
    expect(family_for_eval(families, "unknown").label).toBe("Other")
  })
})

describe("order_families", () => {
  const family = (id: string, label: string) => ({ id, label })

  it("is alphabetical, with Other last", () => {
    const ordered = order_families([
      family("workflow", "Workflow"),
      family(OTHER_FAMILY_ID, "Other"),
      family("format", "Format"),
      family("data_integrity", "Data Integrity"),
    ])
    expect(ordered.map((f) => f.label)).toEqual([
      "Data Integrity",
      "Format",
      "Workflow",
      "Other",
    ])
  })

  it("dedupes, so a family with many evals still claims one place", () => {
    const ordered = order_families([
      family("format", "Format"),
      family("format", "Format"),
      family("workflow", "Workflow"),
    ])
    expect(ordered).toHaveLength(2)
  })

  it("depends only on which families exist, never on how many axes each has", () => {
    const lopsided = order_families([
      family("workflow", "Workflow"),
      family("format", "Format"),
      family("format", "Format"),
      family("format", "Format"),
    ])
    const even = order_families([
      family("format", "Format"),
      family("workflow", "Workflow"),
    ])
    expect(lopsided.map((f) => f.id)).toEqual(even.map((f) => f.id))
  })
})

describe("family_rank", () => {
  it("sorts axes into contiguous runs", () => {
    const ordered = order_families([
      { id: "format", label: "Format" },
      { id: "workflow", label: "Workflow" },
      { id: OTHER_FAMILY_ID, label: "Other" },
    ])
    const ids = ["workflow", OTHER_FAMILY_ID, "format", "workflow"]
    const sorted = [...ids].sort(
      (a, b) => family_rank(ordered, a) - family_rank(ordered, b),
    )
    expect(sorted).toEqual(["format", "workflow", "workflow", OTHER_FAMILY_ID])
  })

  it("puts an unknown family last rather than first", () => {
    const ordered = order_families([{ id: "format", label: "Format" }])
    expect(family_rank(ordered, "nope")).toBeGreaterThanOrEqual(ordered.length)
  })
})
