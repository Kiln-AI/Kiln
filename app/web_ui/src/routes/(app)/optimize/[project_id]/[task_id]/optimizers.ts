import { goto } from "$app/navigation"

export interface Optimizer {
  title: string
  description: string
  info_description?: string
  cost: number
  complexity: number
  speed: number
  onClick: () => void
}

export function get_optimizers(
  project_id: string,
  task_id: string,
): Optimizer[] {
  const optimizers: Optimizer[] = [
    {
      title: "Optimize Prompt",
      description:
        "Automatically optimize your prompt with Kiln Copilot or manually engineer prompts to compare.",
      cost: 4,
      complexity: 1,
      speed: 4,
      onClick: () => {
        goto(`/prompts/${project_id}/${task_id}`)
      },
    },
    {
      title: "Compare Models",
      description: "Find a better, faster or cheaper model for your task.",
      cost: 2,
      complexity: 2,
      speed: 3,
      onClick: () => {
        goto(`/models`)
      },
    },
    {
      title: "Fine Tune",
      description:
        "Learns from your dataset to create custom models. Fine-tuned models can be faster, cheaper and more accurate than standard models.",
      cost: 5,
      complexity: 5,
      speed: 4,
      onClick: () => {
        goto(`/fine_tune/${project_id}/${task_id}`)
      },
    },
    {
      title: "Search Tools (RAG)",
      description:
        "Allow your AI task to search for custom knowledge before answering.",
      cost: 3,
      complexity: 5,
      speed: 4,
      onClick: () => {
        goto(`/docs/${project_id}`)
      },
    },
    {
      title: "MCP Tools",
      description:
        "Add tools like web-search and code interpreter to improve task performance.",
      cost: 1,
      complexity: 2,
      speed: 2,
      onClick: () => {
        goto(`/settings/manage_tools/${project_id}/add_tools`)
      },
    },
    {
      title: "Agents",
      description:
        "Break complex problems into coordinated subtasks with Kiln Tasks as Tools.",
      cost: 1,
      complexity: 2,
      speed: 2,
      onClick: () => {
        goto(`/settings/manage_tools/${project_id}/add_tools/kiln_task`)
      },
    },
  ]
  return optimizers
}
