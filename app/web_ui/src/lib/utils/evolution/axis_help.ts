// What a radar axis actually MEASURES, for the popup that appears when the
// reader hovers its name.
//
// An axis label is a short name - "Refetched Schema", "Cache Hit Rate", "Cache
// Reuse" - and short names are the only ones a ring of thirty will fit. The
// cost is that nothing anywhere on the page says what the criterion behind one
// of them is, so reading the chart means leaving it for the eval's own page and
// coming back. This module is that missing sentence, and both radars render it
// through echarts' own tooltip, so it is the same box the data points already
// use rather than a second popup style.
//
// The two tracks answer the question from different places, and the asymmetry
// is structural rather than an omission:
//
//   - a QUALITY axis is a criterion the task's authors wrote down. Kiln already
//     holds that writing as a Spec, and a spec names the eval it arms, so the
//     description is data we have and did not invent. See `spec_description`
//     for which of a spec's fields is the human one.
//   - a PERFORMANCE axis has no spec by design: the measurement-lane evals are
//     deliberately spec-less, and the quantities are ours rather than the
//     task's. Their description therefore comes from the catalog that already
//     names them - see `metric_axis_help`, which spends nothing but what
//     `MetricAxis` already carries.
//
// A quality axis whose eval has no spec is not an error either: spec/eval is
// 1:1 by convention in a task like Nova, but nothing enforces it, and a
// spec-less eval routes through the `legacy` sentinel and lands in the "Other"
// family. So the resolution below degrades a step at a time - description, then
// just the eval it came from, then no popup at all - rather than rendering an
// empty box.

import type { components } from "$lib/api_schema"
import type { MetricAxis } from "./metric_axes"
import {
  spec_field_configs,
  type FieldConfig,
} from "../../../routes/(app)/specs/[project_id]/[task_id]/select_template/spec_templates"
import type { SpecType } from "$lib/types"

type Spec = components["schemas"]["Spec"]

/** Which end of a score's own scale is the good one */
export type AxisDirection = "higher" | "lower"

/** One axis's popup, before it is turned into HTML */
export interface AxisHelp {
  /** The axis's full name - not the wrapped, possibly ellipsized drawn one */
  title: string
  /** Where the number comes from: the eval, or the quantity behind the virtue */
  subtitle: string | null
  /**
   * Which way the score reads, or null when no direction is in force.
   *
   * One rule on both charts, and it is the one that cannot contradict the
   * picture: this states the direction the axis is PLOTTED with. The quality
   * radar draws "further from the centre is better" and the metrics chart
   * "longer is better", so every axis on either of them has resolved a
   * direction before it was drawn - the quality ring by taking the score's
   * declared one (and higher-is-better for a key nobody declared, which is
   * what every rating scale is), the metrics chart by pointing the catalog's
   * quantity. Null is therefore not the ordinary case: it is for a
   * popup built for an axis that was never plotted, where there is no
   * direction to report and inventing one would be the only way to get it
   * wrong.
   *
   * A consequence worth stating: an INFORMATIONAL score that the metric
   * catalog can point does reach the metrics chart, and this line reports the
   * direction it is drawn with - the same fact the sentence under it already
   * spells out. One the catalog cannot point never reaches either chart (see
   * `directionless_key_count`), and an informational quality score is left off
   * the quality ring entirely, so neither gets a line here.
   */
  direction: AxisDirection | null
  /** What the axis measures, in prose */
  description: string | null
}

/**
 * How much of a description a hover popup carries.
 *
 * Specs are written to be read on their own page, not in a box beside the
 * pointer: Nova's run 95 to 822 characters, and a `definition` fallback can run
 * to 3,700. The popup is a pointer to the criterion, not a replacement for the
 * spec, so it is cut at a word boundary and the rest stays where it was
 * written. 600 is where Nova's own distribution sits - it leaves all but the
 * longest four untouched - and it is about fifteen lines at the width below,
 * which still reads as a tooltip rather than a document.
 */
export const MAX_DESCRIPTION_CHARS = 600

/** How wide the popup is allowed to get. Narrow enough to read as a tooltip. */
const POPUP_WIDTH_PX = 320

/**
 * The direction line, as the reader sees it.
 *
 * Capitals and letter-spacing rather than a sentence: this is the one line in
 * the box that is a PROPERTY of the axis rather than prose about it, and it has
 * to survive being read at a glance while the pointer is still moving. Small
 * and grey keeps it a label - it sits between the eval's name and the
 * criterion, and it must not compete with either.
 */
const DIRECTION_LABELS: Record<AxisDirection, string> = {
  higher: "HIGHER IS BETTER",
  lower: "LOWER IS BETTER",
}

/**
 * The spec's human description.
 *
 * A spec carries the same criterion twice. `definition` is the detailed one,
 * and for a spec the product built it is every property concatenated under
 * `## Heading` markdown - which is a document, not a sentence, and reads badly
 * unrendered in a tooltip. The properties hold the same text in parts, and the
 * FIRST field of the spec type's own field config is the required one the spec
 * builder asks for first: "Issue Description" for an issue, "Desired Behaviour
 * Description" for a desired behaviour. That is the one a reader wants.
 *
 * `spec_field_configs` is the product's table rather than one written here, so
 * a spec type that grows a field, or reorders its form, moves this with it.
 *
 * `definition` is still the fallback, for two cases that are both real: a spec
 * type this build does not know about, and a spec whose properties arrived from
 * somewhere other than the spec builder. It is required and non-empty on every
 * spec, so the fallback always has something to return.
 */
export function spec_description(spec: Spec | null | undefined): string | null {
  if (!spec) return null

  const properties = spec.properties as Record<string, unknown> | null
  const spec_type = properties?.spec_type
  // Indexed by a string off the wire, so the entry may not exist however the
  // table is typed - a spec type newer than this build has no config here
  const fields: FieldConfig[] | undefined =
    typeof spec_type === "string"
      ? spec_field_configs[spec_type as SpecType]
      : undefined
  for (const field of fields ?? []) {
    const value = properties?.[field.key]
    if (typeof value === "string" && value.trim().length > 0) {
      return clamp_description(value.trim())
    }
  }

  const definition = spec.definition?.trim()
  return definition ? clamp_description(definition) : null
}

/**
 * A description cut to length at a word boundary.
 *
 * Cut at a space rather than mid-word, and only when there is a space late
 * enough to be worth honouring - a run of 600 characters with no space in it is
 * not prose, and truncating it to the last space at character 12 would throw
 * the whole thing away.
 */
export function clamp_description(
  text: string,
  max: number = MAX_DESCRIPTION_CHARS,
): string {
  if (text.length <= max) return text
  const cut = text.slice(0, max)
  const space = cut.lastIndexOf(" ")
  const kept = space > max * 0.6 ? cut.slice(0, space) : cut
  return `${kept.replace(/[.,;:\s]+$/, "")}…`
}

/**
 * The popup for a quality axis, or null when there is nothing to say.
 *
 * Null is a real answer and the reason this returns one: an axis whose eval has
 * no spec AND whose eval is named the same thing the axis already says would
 * pop up a box that repeats the label back. Nothing is better than that.
 *
 * The direction does not change that test, and deliberately: every quality axis
 * has one, so counting it as something-to-say would give a popup to exactly the
 * axes the rule above exists to spare. It rides along on a box that had its own
 * reason to open.
 */
export function quality_axis_help(
  label: string,
  evalName: string | null | undefined,
  description: string | null | undefined,
  direction?: string | null,
): AxisHelp | null {
  const title = label.trim()
  const name = evalName?.trim() ?? ""
  // An eval named after its only criterion tells the reader nothing they are
  // not already looking at
  const subtitle = name && name !== title ? name : null
  const body = description?.trim() || null
  if (!subtitle && !body) return null
  return {
    title,
    subtitle,
    direction: quality_axis_direction(direction),
    description: body,
  }
}

/**
 * A `ScoreDirection` off the wire as the direction its axis is drawn with.
 *
 * The two defaults are the chart's, not this module's, and they are why the
 * mapping is a function rather than a lookup: the quality radar treats a key it
 * has no direction for as higher-is-better (a rating scale is higher-is-better
 * by definition, and that is how the axis is then plotted), and it leaves an
 * informational score off the ring altogether rather than drawing a score with
 * no better end. So an unknown direction reports "higher" - the same thing the
 * geometry is already saying - and an informational one reports nothing.
 */
function quality_axis_direction(
  direction: string | null | undefined,
): AxisDirection | null {
  if (direction === "informational") return null
  if (direction === "lower_is_better") return "lower"
  return "higher"
}

/**
 * The popup for a performance axis.
 *
 * There is never a spec here - the measurement-lane evals are spec-less on
 * purpose - so this is assembled from what `MetricAxis` already carries, and
 * nothing new is authored for it. That turns out to be exactly the question the
 * label raises: every axis is named for the VIRTUE ("Narration Consistency"),
 * which is what makes "a longer bar is better" true on all sixteen of them,
 * and the cost of that naming is that the raw quantity ("Longest
 * Silent Run") is no longer on the chart at all. The subtitle is the same
 * `quantity · source` line the data-point tooltip already prints, so the two
 * boxes agree, and the sentence under it is the one fact the label inverts:
 * which end of the raw scale is the good one.
 *
 * Never null. Every axis has a virtue, a quantity and a direction by
 * construction, so there is always something to say.
 */
export function metric_axis_help(axis: MetricAxis): AxisHelp {
  const source = axis.evalName ?? "usage rollup"
  return {
    title: axis.label,
    subtitle: `${axis.valueLabel} · ${source}`,
    // Never null here: an axis on this ring has been pointed, or it would not
    // have been built - see plottable_score_axes
    direction: axis.better,
    description: `${
      axis.better === "higher" ? "Higher" : "Lower"
    } ${mid_sentence(axis.valueLabel)} draws a longer bar.`,
  }
}

/**
 * A title-cased quantity as it reads inside a sentence: "Total Tokens" ->
 * "total tokens". An acronym that arrived capitalized keeps its capitals, so
 * "LLM Calls" does not come out as "llm calls" - the same courtesy
 * `family_label` extends to a family id.
 */
function mid_sentence(label: string): string {
  return label
    .split(" ")
    .map((word) =>
      word.length > 1 && word === word.toUpperCase()
        ? word
        : word.toLowerCase(),
    )
    .join(" ")
}

function escape_html(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

/**
 * The popup as echarts tooltip HTML.
 *
 * Shaped like the data-point tooltips both charts already build - bold name,
 * grey line under it - so hovering a label and hovering a point feel like two
 * views of the same object rather than two features.
 *
 * Four lines at most, in the order a reader needs them: what the axis is called,
 * where its number comes from, WHICH WAY IT READS, and then the criterion in
 * prose. The direction goes above the description rather than below it because
 * it is the shortest answer to the question a radar axis raises first - is a
 * long spoke here good news? - and a reader who has that can stop.
 *
 * The width and `white-space` are set here rather than left to the tooltip,
 * whose container is `white-space: nowrap` and unbounded: a 600-character
 * paragraph would otherwise be laid out as one line several thousand pixels
 * wide, and `confine` would slide the box left until only its end was visible.
 *
 * Escaped, unlike the value tooltips beside it, because this text is the only
 * one on either chart that a person wrote as prose - a spec that mentions a
 * `<tag>` or an ampersand is ordinary, and it must not be able to reach the
 * tooltip as markup.
 */
export function axis_help_html(help: AxisHelp): string {
  let html = `<div style="max-width: ${POPUP_WIDTH_PX}px; white-space: normal;">`
  html += `<div style="font-weight: bold;">${escape_html(help.title)}</div>`
  if (help.subtitle) {
    html += `<div style="color: #888;">${escape_html(help.subtitle)}</div>`
  }
  if (help.direction) {
    html += `<div style="color: #888; font-size: 11px; font-weight: 600; letter-spacing: 0.06em; padding-top: 5px;">${
      DIRECTION_LABELS[help.direction]
    }</div>`
  }
  if (help.description) {
    html += `<div style="padding-top: 6px;">${escape_html(
      help.description,
    )}</div>`
  }
  return `${html}</div>`
}

/**
 * Each eval's description, keyed by the eval its spec arms.
 *
 * Built once by the page that already fetched the specs, so neither chart has
 * to know what a spec is - they take strings. A spec with no eval is a
 * criterion nobody armed: it has no axis, so it is skipped rather than keyed
 * under null.
 */
export function spec_descriptions_by_eval(
  specs: Spec[] | null | undefined,
): Record<string, string> {
  const descriptions: Record<string, string> = {}
  for (const spec of specs ?? []) {
    if (!spec.eval_id) continue
    const description = spec_description(spec)
    if (description) descriptions[spec.eval_id] = description
  }
  return descriptions
}
