// Field configuration for skill properties display
export type FieldConfig = {
  key: string
  label: string
  description: string
}

export const skill_field_configs: FieldConfig[] = [
  {
    key: "description",
    label: "Description",
    description: "A description of when an agent should use this skill.",
  },
  {
    key: "body",
    label: "Instructions",
    description:
      "The markdown content the agent reads when it loads this skill. This is only loaded into context when the agent chooses to use the skill.",
  },
]
