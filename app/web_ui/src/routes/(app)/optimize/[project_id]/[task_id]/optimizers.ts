import { goto } from "$app/navigation"

export const METRIC_IMPACT = "Impact"
export const METRIC_COST_EFFICIENCY = "Cost Efficiency"
export const METRIC_SIMPLICITY = "Simplicity"

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
      title: "Improve Prompt",
      description:
        "Improve output quality by refining instructions, structure, and examples. Best first step before changing models or tools.",
      metrics: { [METRIC_IMPACT]: 5, [METRIC_COST_EFFICIENCY]: 3, [METRIC_SIMPLICITY]: 3 },
      on_click: () => {
        goto(`/prompts/${project_id}/${task_id}`)
      }
    },
    {
      title: "Try Different Models",
      description:
        "Test different models to improve reasoning, structured output, speed, or cost for the same task.",
      metrics: { [METRIC_IMPACT]: 4, [METRIC_COST_EFFICIENCY]: 4, [METRIC_SIMPLICITY]: 1 },
      on_click: () => {
        goto(`/models`)
      }
    },
    {
      title: "Fine-Tune a Model",
      description:
        "Train a custom model on your data for higher accuracy, consistency, and domain-specific performance at scale.",
      metrics: { [METRIC_IMPACT]: 4, [METRIC_COST_EFFICIENCY]: 2, [METRIC_SIMPLICITY]: 1 },
      on_click: () => {
        goto(`/fine_tune/${project_id}/${task_id}`)
      }
    },
    {
      title: "Add Knowledge (RAG)",
      description:
        "Ground responses in your documents and data to reduce hallucinations and improve factual accuracy with Search Tools (RAG).",
      metrics: { [METRIC_IMPACT]: 4, [METRIC_COST_EFFICIENCY]: 2, [METRIC_SIMPLICITY]: 1 },
      on_click: () => {
        goto(`/docs/${project_id}`)
      }
    },
    {
      title: "Add External Tools",
      description:
        "Give your task access to external capabilities like web search, code execution, and system integrations with MCP Tools.",
      metrics: { [METRIC_IMPACT]: 3, [METRIC_COST_EFFICIENCY]: 4, [METRIC_SIMPLICITY]: 2 },
      on_click: () => {
        window.open("https://docs.kiln.tech/docs/tools-and-mcp", "_blank")
      }
    },
    {
      title: "Build an Agent Workflow",
      description:
        "Break complex workflows into coordinated subtasks using multiple models and tools working together with Kiln Tasks as Tools.",
      metrics: { [METRIC_IMPACT]: 4, [METRIC_COST_EFFICIENCY]: 3, [METRIC_SIMPLICITY]: 2 },
      on_click: () => {
        window.open("https://docs.kiln.tech/docs/agents", "_blank")
      }
    },
  ]
  return optimizers
}
