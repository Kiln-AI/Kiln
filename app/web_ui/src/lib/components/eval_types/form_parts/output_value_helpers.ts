export type OutputSource = "final_message" | "trace"

export interface OutputValueState {
  source: OutputSource
  selector: string
}

/**
 * Join a selector to a source prefix.
 * If selector starts with "[", append directly (e.g. "final_message[0]").
 * Otherwise, prepend "." (e.g. "final_message.user.status").
 */
export function joinSelector(selector: string): string {
  const trimmed = selector.trim()
  if (!trimmed) return ""
  if (trimmed.startsWith("[")) return trimmed
  return "." + trimmed
}

/**
 * Emit: convert UI state (source + selector) to the value_expression string.
 */
export function emitValue(state: OutputValueState): string | null {
  const trimmedSelector = state.selector.trim()

  if (state.source === "final_message") {
    if (!trimmedSelector) return null
    return "final_message" + joinSelector(trimmedSelector)
  }

  // source === "trace"
  if (!trimmedSelector) return "trace"
  return "trace" + joinSelector(trimmedSelector)
}

/**
 * Parse: convert a value_expression string back to UI state (source + selector).
 */
export function parseValue(value: string | null | undefined): OutputValueState {
  if (value === null || value === undefined || value.trim() === "") {
    return { source: "final_message", selector: "" }
  }

  const v = value.trim()

  if (v === "final_message") {
    return { source: "final_message", selector: "" }
  }
  if (v.startsWith("final_message.")) {
    return {
      source: "final_message",
      selector: v.slice("final_message.".length),
    }
  }
  if (v.startsWith("final_message[")) {
    return {
      source: "final_message",
      selector: v.slice("final_message".length),
    }
  }

  if (v === "trace") {
    return { source: "trace", selector: "" }
  }
  if (v.startsWith("trace.")) {
    return { source: "trace", selector: v.slice("trace.".length) }
  }
  if (v.startsWith("trace[")) {
    return { source: "trace", selector: v.slice("trace".length) }
  }

  // Legacy / unknown prefix: treat as Final Message with the whole value as selector.
  return { source: "final_message", selector: v }
}
