import { describe, it, expect } from "vitest"
import {
  axis_help_html,
  clamp_description,
  metric_axis_help,
  quality_axis_help,
  spec_description,
  spec_descriptions_by_eval,
  MAX_DESCRIPTION_CHARS,
} from "./axis_help"
import type { MetricAxis } from "./metric_axes"
import type { components } from "$lib/api_schema"

type Spec = components["schemas"]["Spec"]

// Only the fields the resolution reads. A real Spec carries a dozen more that
// none of this touches.
function spec(overrides: Partial<Spec> & Pick<Spec, "properties">): Spec {
  return {
    v: 1,
    name: "A spec",
    definition: "The detailed definition.",
    priority: 1,
    status: "active",
    tags: [],
    eval_id: "eval_1",
    model_type: "spec",
    ...overrides,
  } as Spec
}

describe("spec_description", () => {
  it("takes the field the spec type's own form asks for first", () => {
    const description = spec_description(
      spec({
        definition: "## Issue Description\nThe long composed definition.",
        properties: {
          spec_type: "issue",
          issue_description: "Internal IDs leaked into user-facing text.",
          issue_examples: "Location$FqHYthW6pA",
        },
      }),
    )
    expect(description).toBe("Internal IDs leaked into user-facing text.")
  })

  it("reads a desired behaviour from its own description field", () => {
    const description = spec_description(
      spec({
        properties: {
          spec_type: "desired_behaviour",
          desired_behaviour_description: "The reply mentions the key facts.",
        },
      }),
    )
    expect(description).toBe("The reply mentions the key facts.")
  })

  it("falls through an empty first field to the next one", () => {
    const description = spec_description(
      spec({
        properties: {
          spec_type: "issue",
          issue_description: "   ",
          issue_examples: "One simple trick!",
        },
      }),
    )
    expect(description).toBe("One simple trick!")
  })

  it("falls back to the definition for a spec type it has no config for", () => {
    const description = spec_description(
      spec({
        definition: "Whatever this criterion turns out to be.",
        properties: {
          spec_type: "a_type_from_a_later_build",
          some_new_field: "Not in any field config.",
        } as unknown as Spec["properties"],
      }),
    )
    expect(description).toBe("Whatever this criterion turns out to be.")
  })

  it("is null for no spec at all", () => {
    expect(spec_description(null)).toBeNull()
    expect(spec_description(undefined)).toBeNull()
  })

  it("clamps a spec written to be read on its own page", () => {
    const long = `${"word ".repeat(400)}end`
    const description = spec_description(
      spec({
        properties: {
          spec_type: "issue",
          issue_description: long,
        },
      }),
    )
    expect(description?.length).toBeLessThanOrEqual(MAX_DESCRIPTION_CHARS + 1)
    expect(description?.endsWith("…")).toBe(true)
  })
})

describe("clamp_description", () => {
  it("leaves a description that already fits alone", () => {
    expect(clamp_description("Short enough.", 50)).toBe("Short enough.")
  })

  it("cuts at a word boundary, not mid-word", () => {
    expect(clamp_description("alpha beta gamma delta", 14)).toBe("alpha beta…")
  })

  it("drops the punctuation the cut landed on", () => {
    expect(clamp_description("alpha, beta, gamma", 8)).toBe("alpha…")
  })

  it("cuts mid-run when there is no late enough space to honour", () => {
    const clamped = clamp_description(`x${"y".repeat(40)} tail`, 20)
    expect(clamped).toBe(`x${"y".repeat(19)}…`)
  })
})

describe("quality_axis_help", () => {
  it("carries the eval name and the spec description", () => {
    expect(
      quality_axis_help(
        "Refetched Schema",
        "Nova — Refetches the same schema",
        "The assistant fetched a type it had already fetched.",
        "higher_is_better",
      ),
    ).toEqual({
      title: "Refetched Schema",
      subtitle: "Nova — Refetches the same schema",
      direction: "higher",
      description: "The assistant fetched a type it had already fetched.",
    })
  })

  it("still says which eval an axis came from when there is no spec", () => {
    expect(
      quality_axis_help(
        "Refetched Schema",
        "Nova — Refetches the same schema",
        null,
        "higher_is_better",
      ),
    ).toEqual({
      title: "Refetched Schema",
      subtitle: "Nova — Refetches the same schema",
      direction: "higher",
      description: null,
    })
  })

  it("drops an eval name that only repeats the axis label", () => {
    expect(
      quality_axis_help(
        "Overall Rating",
        " Overall Rating ",
        "Graded 1-5.",
        "higher_is_better",
      ),
    ).toEqual({
      title: "Overall Rating",
      subtitle: null,
      direction: "higher",
      description: "Graded 1-5.",
    })
  })

  it("reports a lower-is-better score as one", () => {
    expect(
      quality_axis_help("Cost", "Nova — Cost", "Dollars.", "lower_is_better")
        ?.direction,
    ).toBe("lower")
  })

  it("reports no direction for an informational score, which has none", () => {
    expect(
      quality_axis_help(
        "Turn 1 Latency",
        "Nova — Latency",
        "ms.",
        "informational",
      )?.direction,
    ).toBeNull()
  })

  it("reports the higher-is-better default the chart already plots", () => {
    // A key with no entry in the directions map is drawn as higher-is-better,
    // so saying so is the geometry rather than a guess about the score
    expect(
      quality_axis_help("Mentions The Key Facts", "Nova — Facts", "Prose.")
        ?.direction,
    ).toBe("higher")
    expect(
      quality_axis_help(
        "Mentions The Key Facts",
        "Nova — Facts",
        "Prose.",
        null,
      )?.direction,
    ).toBe("higher")
  })

  it("is null when the popup would only repeat the label back", () => {
    expect(
      quality_axis_help("Overall Rating", "Overall Rating", null),
    ).toBeNull()
    expect(quality_axis_help("Overall Rating", null, "  ")).toBeNull()
    expect(quality_axis_help("Overall Rating", undefined, undefined)).toBeNull()
    // A direction alone is not a reason to open a box: every axis has one
    expect(
      quality_axis_help(
        "Overall Rating",
        "Overall Rating",
        null,
        "lower_is_better",
      ),
    ).toBeNull()
  })
})

describe("metric_axis_help", () => {
  const axis = (overrides: Partial<MetricAxis>): MetricAxis => ({
    key: "eval_1::max_silent_run",
    label: "Narration Consistency",
    valueLabel: "Longest Silent Run",
    quantity: "max_silent_run",
    family: "responsiveness",
    source: "score",
    unit: "count",
    better: "lower",
    evalName: "Nova — Efficiency",
    ...overrides,
  })

  it("names the raw quantity the virtue is hiding, and its source", () => {
    expect(metric_axis_help(axis({}))).toEqual({
      title: "Narration Consistency",
      subtitle: "Longest Silent Run · Nova — Efficiency",
      direction: "lower",
      description: "Lower longest silent run draws a longer bar.",
    })
  })

  it("takes the direction the axis is plotted with", () => {
    expect(metric_axis_help(axis({ better: "higher" })).direction).toBe(
      "higher",
    )
    expect(metric_axis_help(axis({ better: "lower" })).direction).toBe("lower")
  })

  it("says the usage rollup when no eval computed it", () => {
    expect(
      metric_axis_help(
        axis({ source: "usage", evalName: null, valueLabel: "Cost" }),
      ).subtitle,
    ).toBe("Cost · usage rollup")
  })

  it("points a higher-is-better metric the other way", () => {
    expect(
      metric_axis_help(
        axis({
          label: "Cache Hit Rate",
          valueLabel: "Cache Hit Rate",
          better: "higher",
        }),
      ).description,
    ).toBe("Higher cache hit rate draws a longer bar.")
  })

  it("keeps an acronym capitalized mid-sentence", () => {
    expect(
      metric_axis_help(
        axis({ label: "LLM Call Economy", valueLabel: "LLM Calls" }),
      ).description,
    ).toBe("Lower LLM calls draws a longer bar.")
  })
})

describe("axis_help_html", () => {
  it("wraps, so a paragraph is not laid out as one very long line", () => {
    const html = axis_help_html({
      title: "Refetched Schema",
      subtitle: "Nova — Refetches the same schema",
      direction: "higher",
      description: "Fetched a type it already had.",
    })
    expect(html).toContain("white-space: normal")
    expect(html).toContain("max-width")
    expect(html).toContain("Refetched Schema")
    expect(html).toContain("Nova — Refetches the same schema")
    expect(html).toContain("Fetched a type it already had.")
  })

  it("states the direction in caps, under the eval and over the criterion", () => {
    const html = axis_help_html({
      title: "Writes One Record At A Time",
      subtitle: "Nova — Writes one record at a time (code)",
      direction: "higher",
      description: "One mutation per id where a batch was available.",
    })
    expect(html).toContain("HIGHER IS BETTER")
    expect(
      html.indexOf("Nova — Writes one record at a time (code)"),
    ).toBeLessThan(html.indexOf("HIGHER IS BETTER"))
    expect(html.indexOf("HIGHER IS BETTER")).toBeLessThan(
      html.indexOf("One mutation per id where a batch was available."),
    )
  })

  it("says the other direction when that is the good end", () => {
    const html = axis_help_html({
      title: "Token Economy",
      subtitle: "Total Tokens · usage rollup",
      direction: "lower",
      description: "Lower total tokens draws a longer bar.",
    })
    expect(html).toContain("LOWER IS BETTER")
    expect(html).not.toContain("HIGHER IS BETTER")
  })

  it("leaves out the lines it has nothing for", () => {
    const html = axis_help_html({
      title: "Speed",
      subtitle: null,
      direction: null,
      description: null,
    })
    expect(html).toContain("Speed")
    expect(html).not.toContain("color: #888")
    expect(html).not.toContain("padding-top")
    expect(html).not.toContain("IS BETTER")
  })

  it("escapes prose, which is the one place a person wrote the text", () => {
    const html = axis_help_html({
      title: "Emits raw chart markup",
      subtitle: null,
      direction: "higher",
      description: 'A <chart> tag & a "quote".',
    })
    expect(html).toContain("&lt;chart&gt; tag &amp; a &quot;quote&quot;")
    expect(html).not.toContain("<chart>")
  })
})

describe("spec_descriptions_by_eval", () => {
  it("keys each description by the eval its spec arms", () => {
    const descriptions = spec_descriptions_by_eval([
      spec({
        eval_id: "eval_a",
        properties: { spec_type: "issue", issue_description: "A leaks." },
      }),
      spec({
        eval_id: "eval_b",
        properties: { spec_type: "issue", issue_description: "B leaks." },
      }),
    ])
    expect(descriptions).toEqual({ eval_a: "A leaks.", eval_b: "B leaks." })
  })

  it("skips a spec nobody armed - it has no axis to describe", () => {
    const descriptions = spec_descriptions_by_eval([
      spec({
        eval_id: null,
        properties: { spec_type: "issue", issue_description: "Never armed." },
      }),
    ])
    expect(descriptions).toEqual({})
  })

  it("is empty for a task with no specs", () => {
    expect(spec_descriptions_by_eval(null)).toEqual({})
    expect(spec_descriptions_by_eval([])).toEqual({})
  })
})
