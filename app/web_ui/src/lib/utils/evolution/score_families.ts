// Families for the quality radar's axes, read from the task's own metadata.
//
// The metrics radar groups its ring from a catalog this repo owns: there are
// only so many things "cost" or "latency" can mean, so the families can be
// curated. Quality is the opposite - the criteria are whatever the task's
// authors decided to measure, and a taxonomy invented in the UI would be a
// guess that disagrees with the specs. So this module does not classify
// anything. It reads a grouping the task already declared and degrades to no
// grouping at all when there is none.
//
// Two sources, in order of precedence:
//
//  1. A FAMILY TAG on the spec. Kiln specs carry free-form tags, and a task
//     that has thought about its criteria in groups tends to have written the
//     grouping down there. A tag of the form `fam_<name>` / `family_<name>`
//     (either separator, any case) declares the family explicitly. This is
//     first because it is the only one where an author said what they meant.
//
//  2. The spec's TYPE - `properties.spec_type`. This is Kiln's own built-in
//     taxonomy: every spec is an issue, a tone, a localization, a
//     hallucinations, and so on. It needs no convention because the data model
//     already carries it, which makes it the sensible default for a task that
//     never adopted a tagging scheme.
//
// ...and then nothing. A task whose specs are all one spec_type and carry no
// family tags gets no bands and no key, and the chart renders exactly as it did
// before families existed. That is the honest outcome: the alternative is a
// grouping the UI made up, which is worse than none.
//
// A source has to actually group to be used: at least two distinct families,
// covering at least half the evals that have a spec at all. One family divides
// nothing, and a scheme two specs out of thirty opted into would file the other
// twenty-eight under "Other" and call it a taxonomy.

import type { components } from "$lib/api_schema"

type Spec = components["schemas"]["Spec"]

export interface ScoreFamily {
  /** Stable id, used to group and to keep bands contiguous */
  id: string
  /** Heading shown in the radar's key and as a table group header */
  label: string
}

/**
 * Where an eval's criteria go when the task groups its specs but this eval was
 * left out of the scheme - no spec, no family tag, or a spec_type nothing else
 * shares. Always ordered last.
 */
export const OTHER_FAMILY_ID = "__other__"
export const OTHER_FAMILY_LABEL = "Other"
export const OTHER_FAMILY: ScoreFamily = {
  id: OTHER_FAMILY_ID,
  label: OTHER_FAMILY_LABEL,
}

// `fam_data_integrity`, `family:tool-routing`, `FAM-Reliability`. The separator
// is permissive because tag conventions vary between teams and the prefix is
// the part carrying the meaning.
const FAMILY_TAG_PATTERN = /^(?:fam|family)[_:-](.+)$/i

/** A share of the specs this small doesn't describe the task, it describes a corner of it */
const MIN_COVERAGE = 0.5

/** The family a spec's tags declare, or null when they declare none */
export function family_from_tags(
  tags: string[] | null | undefined,
): string | null {
  for (const tag of tags ?? []) {
    const match = FAMILY_TAG_PATTERN.exec(tag.trim())
    if (match && match[1].trim().length > 0) {
      return match[1].trim().toLowerCase()
    }
  }
  return null
}

/**
 * A family id as a heading: `data_integrity` -> "Data Integrity".
 *
 * Derived rather than looked up, because the ids come from the task rather than
 * from us and there is no table that could cover them. Acronyms are left alone
 * when they arrive already capitalized, so a task that tagged `fam_PII` keeps
 * it rather than being title-cased into "Pii".
 */
export function family_label(id: string): string {
  return id
    .split(/[_:\-\s]+/)
    .filter((word) => word.length > 0)
    .map((word) =>
      word === word.toUpperCase() && word.length > 1
        ? word
        : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase(),
    )
    .join(" ")
}

/** The spec_type a spec declares, if its properties carry one */
function spec_type_of(spec: Spec): string | null {
  const properties = spec.properties as { spec_type?: unknown } | null
  const value = properties?.spec_type
  return typeof value === "string" && value.length > 0 ? value : null
}

/** eval id -> family id, for the specs that declare one under this source */
function assign(
  specs: Spec[],
  familyOf: (spec: Spec) => string | null,
): Map<string, string> {
  const assignment = new Map<string, string>()
  for (const spec of specs) {
    // A spec with no eval is a criterion nobody armed - it has no score key on
    // the chart, so it neither gets a family nor counts against coverage.
    if (!spec.eval_id) continue
    const family = familyOf(spec)
    if (family) {
      assignment.set(spec.eval_id, family)
    }
  }
  return assignment
}

/** Whether an assignment actually groups the task, rather than a corner of it */
function usable(assignment: Map<string, string>, evalCount: number): boolean {
  if (evalCount === 0) return false
  const distinct = new Set(assignment.values())
  return (
    distinct.size >= 2 && assignment.size >= Math.ceil(evalCount * MIN_COVERAGE)
  )
}

/**
 * eval id -> family, for every eval the task's specs group.
 *
 * Empty when the task declares no usable grouping, which the callers read as
 * "no families": the radar draws no bands and no key, and the table renders one
 * ungrouped list. Evals inside a grouped task that the scheme missed are absent
 * from the map too, and the callers file those under `OTHER_FAMILY`.
 */
export function build_score_families(
  specs: Spec[] | null | undefined,
): Map<string, ScoreFamily> {
  const all = (specs ?? []).filter((spec) => !!spec.eval_id)
  const evalCount = new Set(all.map((spec) => spec.eval_id as string)).size

  const by_tag = assign(all, (spec) => family_from_tags(spec.tags))
  const chosen = usable(by_tag, evalCount)
    ? by_tag
    : (() => {
        const by_type = assign(all, spec_type_of)
        return usable(by_type, evalCount) ? by_type : new Map<string, string>()
      })()

  const families = new Map<string, ScoreFamily>()
  for (const [evalId, id] of chosen) {
    families.set(evalId, { id, label: family_label(id) })
  }
  return families
}

/**
 * The family an eval's scores belong to. `OTHER_FAMILY` for an eval the task's
 * scheme did not reach - never null, so callers ordering or heading a row never
 * have to special-case it.
 */
export function family_for_eval(
  families: Map<string, ScoreFamily>,
  evalId: string,
): ScoreFamily {
  return families.get(evalId) ?? OTHER_FAMILY
}

/**
 * Ring order for the families in play.
 *
 * Alphabetical, with "Other" last. The metrics ring has a curated order that
 * tells a story - what it cost, what it spent, how many trips, how long - and
 * these families have no such narrative available, because they came from the
 * task rather than from us. So the order is the one a reader can predict
 * without being told, and it is stable: it depends only on which families
 * exist, never on how many axes each has or which run configs are pinned, so
 * pinning a config cannot make the ring reshuffle.
 */
export function order_families(families: ScoreFamily[]): ScoreFamily[] {
  const seen = new Map<string, ScoreFamily>()
  for (const family of families) {
    if (!seen.has(family.id)) seen.set(family.id, family)
  }
  return [...seen.values()].sort((a, b) => {
    const a_other = a.id === OTHER_FAMILY_ID ? 1 : 0
    const b_other = b.id === OTHER_FAMILY_ID ? 1 : 0
    return a_other - b_other || a.label.localeCompare(b.label)
  })
}

/** Position of a family in ring order, for sorting axes or table rows */
export function family_rank(ordered: ScoreFamily[], id: string): number {
  const index = ordered.findIndex((family) => family.id === id)
  return index === -1 ? ordered.length : index
}
