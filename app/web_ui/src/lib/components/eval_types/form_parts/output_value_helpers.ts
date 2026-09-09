export type OutputMode = "final_message" | "trace" | "custom"

export interface OutputValueState {
  mode: OutputMode
  customText: string
}

/**
 * The six canonical Jinja expression examples shown in the examples modal.
 */
export const JINJA_EXAMPLES: { label: string; expression: string }[] = [
  {
    label: "Extract a field from JSON",
    expression: "(final_message | fromjson).user.status",
  },
  {
    label: "Truncate a long output",
    expression: "final_message | truncate(200)",
  },
  {
    label: "Last message in the trace",
    expression: "trace[-1].content",
  },
  {
    label: "Uppercase the output",
    expression: "final_message | upper",
  },
  {
    label: "Count messages in the trace",
    expression: "trace | length",
  },
  {
    label: "Tool call name in the trace",
    expression: "trace[-1].tool_calls[0].function.name",
  },
]

/**
 * Emit: convert UI state (mode + customText) to the value_expression string.
 */
export function emitValue(state: OutputValueState): string | null {
  switch (state.mode) {
    case "final_message":
      return "final_message"
    case "trace":
      return "trace"
    case "custom":
      return state.customText.trim() || null
  }
}

/**
 * Parse: convert a value_expression string back to UI state (mode + customText).
 */
export function parseValue(value: string | null | undefined): OutputValueState {
  if (value === null || value === undefined || value.trim() === "") {
    return { mode: "final_message", customText: "" }
  }

  const v = value.trim()

  if (v === "final_message") {
    return { mode: "final_message", customText: "" }
  }

  if (v === "trace") {
    return { mode: "trace", customText: "" }
  }

  // Anything else is custom
  return { mode: "custom", customText: v }
}
