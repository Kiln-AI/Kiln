import { goto } from "$app/navigation"

export const METRIC_COST = "Cost"
export const METRIC_EFFORT = "Effort"

export interface Optimizer {
  title: string
  description: string
  metrics: Record<string, number>
  recommended?: boolean
  recommended_tooltip?: string
}

export function get_optimizers(
  project_id: string,
  task_id: string,
): Optimizer[] {
  const optimizers: Optimizer[] = [
    {
      title: "Improve Prompt",
      description:
        "Improve output quality by refining instructions, structure, and examples.",
      metrics: { [METRIC_COST]: 4, [METRIC_EFFORT]: 1 },
      recommended: true,
      recommended_tooltip: "Best first step before changing models or tools.",
    },
    {
      title: "Try Different Models",
      description:
        "Test different models to improve reasoning, structured output, speed, or cost for the same task.",
      metrics: { [METRIC_COST]: 2, [METRIC_EFFORT]: 2 },
    },
    {
      title: "Fine-Tune a Model",
      description:
        "Train a custom model on your data for higher accuracy, consistency, and domain-specific performance at scale.",
      metrics: { [METRIC_COST]: 5, [METRIC_EFFORT]: 5 },
    },
    {
      title: "Add Knowledge (RAG)",
      description:
        "Ground responses in your documents and data to reduce hallucinations and improve factual accuracy with Search Tools (RAG).",
      metrics: { [METRIC_COST]: 3, [METRIC_EFFORT]: 4 },
    },
    {
      title: "Add External Tools",
      description:
        "Give your task access to external capabilities like web search, code execution, and system integrations with MCP Tools.",
      metrics: { [METRIC_COST]: 1, [METRIC_EFFORT]: 2 },
    },
    {
      title: "Build an Agent Workflow",
      description:
        "Break complex workflows into coordinated subtasks using multiple models and tools working together with Kiln Tasks as Tools.",
      metrics: { [METRIC_COST]: 1, [METRIC_EFFORT]: 3 },
    },
  ]
  return optimizers
}
