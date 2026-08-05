import type { Spec } from "$lib/types"

export type Breadcrumb = {
  label: string
  href: string
}

export function buildCreateEvalBreadcrumbs(
  project_id: string,
  task_id: string,
  spec_id: string,
  eval_id: string,
  spec: Spec | null | undefined,
  next_page: string | null,
): Breadcrumb[] {
  const crumbs: Breadcrumb[] = [
    {
      label: "Evals",
      href: `/specs/${project_id}/${task_id}`,
    },
    {
      label: spec?.name || "Eval",
      href: `/specs/${project_id}/${task_id}/${spec_id}`,
    },
    {
      label: "Eval",
      href: `/specs/${project_id}/${task_id}/${spec_id}/${eval_id}`,
    },
  ]

  if (next_page === "eval_configs") {
    crumbs.push({
      label: "Compare Judges",
      href: `/specs/${project_id}/${task_id}/${spec_id}/${eval_id}/eval_configs`,
    })
  } else if (next_page === "compare_run_configs") {
    crumbs.push({
      label: "Compare Run Configurations",
      href: `/specs/${project_id}/${task_id}/${spec_id}/${eval_id}/compare_run_configs`,
    })
  }

  return crumbs
}
