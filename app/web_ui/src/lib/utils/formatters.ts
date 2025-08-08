import {
  type EvalConfigType,
  type StructuredOutputMode,
  type ToolType,
} from "$lib/types"

export function formatDate(dateString: string | undefined): string {
  if (!dateString) {
    return "Unknown"
  }
  const date = new Date(dateString)
  const time_ago = Date.now() - date.getTime()

  if (time_ago < 1000 * 60) {
    return "just now"
  }
  if (time_ago < 1000 * 60 * 2) {
    return "1 minute ago"
  }
  if (time_ago < 1000 * 60 * 60) {
    return `${Math.floor(time_ago / (1000 * 60))} minutes ago`
  }
  if (date.toDateString() === new Date().toDateString()) {
    return (
      date.toLocaleString(undefined, {
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      }) + " today"
    )
  }

  const options: Intl.DateTimeFormatOptions = {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }

  const formattedDate = date.toLocaleString(undefined, options)
  // Helps on line breaks with CA/US locales
  return formattedDate
    .replace(" AM", "am")
    .replace(" PM", "pm")
    .replace(",", "")
}

export function eval_config_to_ui_name(
  eval_config_type: EvalConfigType,
): string {
  return (
    {
      g_eval: "G-Eval",
      llm_as_judge: "LLM as Judge",
    }[eval_config_type] || eval_config_type
  )
}

export function data_strategy_name(data_strategy: string): string {
  switch (data_strategy) {
    case "final_only":
      return "Standard"
    case "final_and_intermediate":
      return "Reasoning (legacy two-message format)"
    case "two_message_cot":
      return "Reasoning (separate thinking message)"
    case "final_and_intermediate_r1_compatible":
      return "Reasoning (R1 format thinking)"
    default:
      return data_strategy
  }
}

export function rating_name(rating_type: string): string {
  switch (rating_type) {
    case "five_star":
      return "5 star"
    case "pass_fail":
      return "Pass/Fail"
    case "pass_fail_critical":
      return "Pass/Fail/Critical"
    default:
      return rating_type
  }
}

/**
 * Converts StructuredOutputMode to a human-readable string.
 * This function uses exhaustive case checking - if you add a new case to StructuredOutputMode,
 * TypeScript will force you to handle it here.
 */
export function structuredOutputModeToString(
  mode: StructuredOutputMode,
): string | undefined {
  switch (mode) {
    case "default":
      return "Default (Legacy)"
    case "json_schema":
      return "JSON Schema"
    case "function_calling_weak":
      return "Weak Function Calling"
    case "function_calling":
      return "Function Calling"
    case "json_mode":
      return "JSON Mode"
    case "json_instructions":
      return "JSON Instructions"
    case "json_instruction_and_object":
      return "JSON Instructions + Mode"
    case "json_custom_instructions":
      return "None"
    case "unknown":
      return "Unknown"
    default: {
      // This ensures exhaustive checking - if you add a new case to StructuredOutputMode
      // and don't handle it above, TypeScript will error here
      const exhaustiveCheck: never = mode
      console.warn(`Unhandled StructuredOutputMode: ${exhaustiveCheck}`)
      return undefined
    }
  }
}

/**
 * Converts ToolType to a human-readable string.
 * This function uses exhaustive case checking - if you add a new case to ToolType,
 * TypeScript will force you to handle it here.
 */
export function toolTypeToString(toolType: ToolType): string | undefined {
  switch (toolType) {
    case "remote_mcp":
      return "Remote MCP"
    default: {
      // This ensures exhaustive checking - if you add a new case to StructuredOutputMode
      // and don't handle it above, TypeScript will error here
      const exhaustiveCheck: never = toolType
      console.warn(`Unhandled toolType: ${exhaustiveCheck}`)
      return undefined
    }
  }
}
