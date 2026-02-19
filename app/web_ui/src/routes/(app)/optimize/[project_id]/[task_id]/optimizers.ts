import { goto } from "$app/navigation"

export const METRIC_IMPACT = "Impact"
export const METRIC_COST_EFFICIENCY = "Cost Efficiency"
export const METRIC_EASE = "Ease"

export interface Optimizer {
  title: string
  description: string
  metrics: Record<string, number>
  on_click: () => void
}

export function get_optimizers(
  project_id: string,
  task_id: string,
): Optimizer[] {
  const optimizers: Optimizer[] = [
    {
      title: "Refine Prompt",
      description:
        "Improve your prompt, manually or using our automatic optimizers.",
      metrics: {
        [METRIC_IMPACT]: 5,
        [METRIC_COST_EFFICIENCY]: 4,
        [METRIC_EASE]: 4,
      },
      on_click: () => {
        goto(
          `/prompts/${project_id}/${task_id}/prompt_generators?from=optimize`,
        )
      },
    },
    {
      title: "Compare Models",
      description:
        "Compare models to find the best quality/cost tradeoff for your task.",
      metrics: {
        [METRIC_IMPACT]: 3,
        [METRIC_COST_EFFICIENCY]: 4,
        [METRIC_EASE]: 2,
      },
      on_click: () => {
        goto(`/models`)
      },
    },
    {
      title: "Fine-Tune",
      description: "Train a custom model for your task.",
      metrics: {
        [METRIC_IMPACT]: 3,
        [METRIC_COST_EFFICIENCY]: 4,
        [METRIC_EASE]: 1,
      },
      on_click: () => {
        goto(`/fine_tune/${project_id}/${task_id}`)
      },
    },
    {
      title: "Add Docs & Search (RAG)",
      description: "Let agents search for relevant knowledge.",
      metrics: {
        [METRIC_IMPACT]: 4,
        [METRIC_COST_EFFICIENCY]: 4,
        [METRIC_EASE]: 3,
      },
      on_click: () => {
        goto(`/docs/${project_id}`)
      },
    },
    {
      title: "Add Tools (MCP)",
      description: "Add tools like web-search, code sandboxes, and more.",
      metrics: {
        [METRIC_IMPACT]: 3,
        [METRIC_COST_EFFICIENCY]: 3,
        [METRIC_EASE]: 2,
      },
      on_click: () => {
        window.open("https://docs.kiln.tech/docs/tools-and-mcp", "_blank")
      },
    },
    {
      title: "Add Sub-Agents",
      description: "Allow your task to call other agents and perform work.",
      metrics: {
        [METRIC_IMPACT]: 4,
        [METRIC_COST_EFFICIENCY]: 4,
        [METRIC_EASE]: 2,
      },
      on_click: () => {
        window.open("https://docs.kiln.tech/docs/agents", "_blank")
      },
    },
  ]
  return optimizers
}
