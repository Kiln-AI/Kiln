import type { Eval, Priority, Spec, SpecStatus } from "$lib/types"

/**
 * Row computation for the evals list page.
 *
 * Pure functions so the table can be a reactive derivation in the page (never
 * an imperative "recompute" call, which would read stale reactive maps) and so
 * the partitioning rules are unit-testable.
 */

export type TableRow =
  | { type: "spec"; data: Spec }
  | { type: "legacy_eval"; data: Eval }

export type SortableColumn =
  | "name"
  | "template"
  | "priority"
  | "status"
  | "created_at"

/**
 * Priority/status live on the eval; the server resolves legacy spec-backed
 * evals through their spec on read. Spec rows look their eval up here, and
 * fall back to the spec's own (legacy) values only if the eval is missing.
 */
export function resolved_priority(
  spec: Spec,
  by_id: Map<string, Eval>,
): Priority {
  return (
    (spec.eval_id ? by_id.get(spec.eval_id)?.priority : null) ?? spec.priority
  )
}

export function resolved_status(
  spec: Spec,
  by_id: Map<string, Eval>,
): SpecStatus {
  return (spec.eval_id ? by_id.get(spec.eval_id)?.status : null) ?? spec.status
}

function getStatusSortOrder(status: SpecStatus): number {
  switch (status) {
    case "active":
      return 0
    case "future":
      return 1
    case "deprecated":
      return 2
    case "archived":
      return 3
    default: {
      const _: never = status
      return 4
    }
  }
}

function row_priority(row: TableRow, by_id: Map<string, Eval>): Priority {
  return row.type === "spec"
    ? resolved_priority(row.data, by_id)
    : row.data.priority ?? 1
}

function row_status(row: TableRow, by_id: Map<string, Eval>): SpecStatus {
  return row.type === "spec"
    ? resolved_status(row.data, by_id)
    : row.data.status ?? "active"
}

function sortFunction(
  a: TableRow,
  b: TableRow,
  by_id: Map<string, Eval>,
  sortColumn: SortableColumn,
  sortDirection: "asc" | "desc",
) {
  let aValue: string | number | Date | null | undefined
  let bValue: string | number | Date | null | undefined

  const aData = a.type === "spec" ? a.data : null
  const bData = b.type === "spec" ? b.data : null
  const aEval = a.type === "legacy_eval" ? a.data : null
  const bEval = b.type === "legacy_eval" ? b.data : null

  switch (sortColumn) {
    case "name":
      aValue = (aData?.name || aEval?.name || "").toLowerCase()
      bValue = (bData?.name || bEval?.name || "").toLowerCase()
      break
    case "template":
      aValue = aData?.properties.spec_type || (aEval ? "none" : "")
      bValue = bData?.properties.spec_type || (bEval ? "none" : "")
      break
    case "priority":
      // Priority is flipped since P0 is the highest priority
      aValue = row_priority(b, by_id)
      bValue = row_priority(a, by_id)
      break
    case "status":
      aValue = getStatusSortOrder(row_status(a, by_id))
      bValue = getStatusSortOrder(row_status(b, by_id))
      break
    case "created_at":
      aValue =
        aData?.created_at || aEval?.created_at
          ? new Date((aData?.created_at || aEval?.created_at)!).getTime()
          : 0
      bValue =
        bData?.created_at || bEval?.created_at
          ? new Date((bData?.created_at || bEval?.created_at)!).getTime()
          : 0
      break
    default:
      return 0
  }

  if (!aValue && aValue !== 0) return sortDirection === "asc" ? 1 : -1
  if (!bValue && bValue !== 0) return sortDirection === "asc" ? -1 : 1

  if (aValue < bValue) return sortDirection === "asc" ? -1 : 1
  if (aValue > bValue) return sortDirection === "asc" ? 1 : -1
  return 0
}

export function compute_table(
  specs: Spec[] | null,
  evals: Eval[] | null,
  by_id: Map<string, Eval>,
  show_archived: boolean,
  filter_tags: string[],
  sortColumn: SortableColumn,
  sortDirection: "asc" | "desc",
): { filtered: Spec[] | null; rows: TableRow[] | null } {
  if (!specs) {
    return { filtered: null, rows: null }
  }

  const active_specs = specs.filter(
    (spec) => resolved_status(spec, by_id) !== "archived",
  )
  const archived_specs = specs.filter(
    (spec) => resolved_status(spec, by_id) === "archived",
  )

  const filtered_active =
    filter_tags.length > 0
      ? active_specs.filter((spec) =>
          filter_tags.every((tag) => spec.tags?.includes(tag)),
        )
      : active_specs

  const filtered_archived =
    filter_tags.length > 0
      ? archived_specs.filter((spec) =>
          filter_tags.every((tag) => spec.tags?.includes(tag)),
        )
      : archived_specs

  const all_specs_to_show = show_archived
    ? [...filtered_active, ...filtered_archived]
    : filtered_active

  const spec_eval_ids = new Set(
    specs.map((spec) => spec.eval_id).filter((id) => id != null),
  )
  const legacy_evals = (evals || []).filter(
    (e) =>
      e.id &&
      !spec_eval_ids.has(e.id) &&
      (show_archived || (e.status ?? "active") !== "archived"),
  )

  const spec_rows: TableRow[] = all_specs_to_show.map((spec) => ({
    type: "spec" as const,
    data: spec,
  }))
  const legacy_eval_rows: TableRow[] = legacy_evals.map((e) => ({
    type: "legacy_eval" as const,
    data: e,
  }))

  const all_rows: TableRow[] = [...spec_rows, ...legacy_eval_rows]
  const rows = [...all_rows].sort((a, b) =>
    sortFunction(a, b, by_id, sortColumn, sortDirection),
  )

  return { filtered: all_specs_to_show, rows }
}
