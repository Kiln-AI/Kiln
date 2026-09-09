// What the compare table shows once the user has adjusted it: whole sections (an
// eval, or the usage/cost section) and individual rows hidden with an ✕, and rows
// renamed for display. Pure functions, so the page's reactive statements stay short
// and this is testable.

export type ComparisonSection = {
  category: string
  eval_id: string
  items: { label: string; key: string }[]
}

// Display names the user has given rows, by row key
export type MetricLabels = Record<string, string>

export type HiddenMetricInfo = {
  key: string
  label: string
  // Name of the section the row belongs to, so "Overall Correct" from one eval can
  // be told apart from the same score name in another
  section: string
}

// A comma-separated list from the URL, trimmed and deduped, with entries that fail
// `isValid` dropped - a hand-edited URL can be messy.
export function parseHiddenListParam(
  value: string | null,
  isValid: (entry: string) => boolean = () => true,
): string[] {
  if (!value) return []
  return [
    ...new Set(
      value
        .split(",")
        .map((entry) => entry.trim())
        .filter((entry) => entry.length > 0 && isValid(entry)),
    ),
  ]
}

// Drop hidden sections, and hidden rows from the sections that remain. A section
// whose rows are all hidden stays, with no items - it still has a header to show
// (and an ✕ of its own). Returns the input untouched when nothing is hidden.
export function filterVisibleSections<T extends ComparisonSection>(
  sections: T[],
  hiddenSectionIds: string[],
  hiddenMetricKeys: string[],
): T[] {
  if (hiddenSectionIds.length === 0 && hiddenMetricKeys.length === 0) {
    return sections
  }
  return sections
    .filter((section) => !hiddenSectionIds.includes(section.eval_id))
    .map((section) =>
      hiddenMetricKeys.length > 0
        ? {
            ...section,
            items: section.items.filter(
              (item) => !hiddenMetricKeys.includes(item.key),
            ),
          }
        : section,
    )
}

// The hidden rows the user can bring back one at a time, in table order. Rows of a
// hidden section are left out: showing one of those would change nothing until the
// section itself is shown again. Keys that match no known row (an eval that no
// longer exists, say) are left out too rather than listed as a raw key.
export function listHiddenMetrics(
  sections: ComparisonSection[],
  hiddenSectionIds: string[],
  hiddenMetricKeys: string[],
): HiddenMetricInfo[] {
  if (hiddenMetricKeys.length === 0) return []
  return sections
    .filter((section) => !hiddenSectionIds.includes(section.eval_id))
    .flatMap((section) =>
      section.items
        .filter((item) => hiddenMetricKeys.includes(item.key))
        .map((item) => ({
          key: item.key,
          label: item.label,
          section: section.category,
        })),
    )
}

// The user's display names from the URL: a JSON object of row key to name. Anything
// that isn't that shape is ignored rather than allowed to break the page.
export function parseMetricLabelsParam(value: string | null): MetricLabels {
  if (!value) return {}
  let parsed: unknown
  try {
    parsed = JSON.parse(value)
  } catch {
    return {}
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return {}
  }
  const labels: MetricLabels = {}
  for (const [key, name] of Object.entries(parsed)) {
    if (typeof name !== "string") continue
    const trimmed = name.trim()
    if (key.includes("::") && trimmed.length > 0) labels[key] = trimmed
  }
  return labels
}

// Rows relabelled with the user's display names, so the name shows everywhere the
// row does. Returns the input untouched when there are none.
export function applyMetricLabels<T extends ComparisonSection>(
  sections: T[],
  labels: MetricLabels,
): T[] {
  if (Object.keys(labels).length === 0) return sections
  return sections.map((section) => ({
    ...section,
    items: section.items.map((item) =>
      labels[item.key] ? { ...item, label: labels[item.key] } : item,
    ),
  }))
}

// The user's new name for a row, folded into the current set. An empty name, or the
// row's own original name, drops the override instead of storing it.
export function withMetricLabel(
  labels: MetricLabels,
  key: string,
  name: string,
  originalLabel: string | undefined,
): MetricLabels {
  const trimmed = name.trim()
  const next = { ...labels }
  if (trimmed.length === 0 || trimmed === originalLabel) {
    delete next[key]
  } else {
    next[key] = trimmed
  }
  return next
}
