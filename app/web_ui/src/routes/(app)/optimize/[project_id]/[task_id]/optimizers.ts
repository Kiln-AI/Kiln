export interface Optimizer {
  title: string
  description: string
  info_description?: string
  cost: number
  complexity: number
  speed: number
  onClick: () => void
}

export const optimizers: Optimizer[] = [
  {
    title: "Optimize Prompt",
    description:
      "Automatically optimize your prompt with Kiln Copilot or manually engineer prompts to compare.",
    cost: 4,
    complexity: 1,
    speed: 4,
    onClick: () => {},
  },
  {
    title: "Compare Models",
    description: "Find a better, faster or cheaper model for your task.",
    cost: 2,
    complexity: 2,
    speed: 3,
    onClick: () => {},
  },
  {
    title: "Fine Tune",
    description:
      "Learns from your dataset to create custom models. Fine-tuned models can be faster, cheaper and more accurate than standard models.",
    cost: 5,
    complexity: 5,
    speed: 4,
    onClick: () => {},
  },
  {
    title: "Search Tools (RAG)",
    description:
      "Allow your AI task to search for custom knowledge before answering.",
    cost: 3,
    complexity: 5,
    speed: 4,
    onClick: () => {},
  },
  {
    title: "MCP Tools",
    description:
      "Add tools like web-search and code interpreter to improve task performance.",
    cost: 1,
    complexity: 2,
    speed: 2,
    onClick: () => {},
  },
  {
    title: "Agents",
    description:
      "Create multi-actor patterns by organizing a hierarchy of tasks.",
    cost: 1,
    complexity: 2,
    speed: 2,
    onClick: () => {},
  },
]
