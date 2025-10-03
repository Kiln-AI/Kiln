import {
  type ChunkerType,
  type EvalConfigType,
  type OutputFormat,
  type StructuredOutputMode,
  type ToolServerType,
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

export function formatSize(byteSize: number | undefined | null): string {
  if (typeof byteSize !== "number" || isNaN(byteSize) || byteSize < 0) {
    return "unknown"
  }

  const units = ["B", "KB", "MB", "GB", "TB"]
  let size = byteSize
  let idx = 0

  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024
    idx += 1
  }

  // Remove trailing .0 from the size
  const formattedSize = idx === 0 ? size.toString() : size.toFixed(1)
  const displaySize = formattedSize.endsWith(".0")
    ? formattedSize.slice(0, -2)
    : formattedSize
  return `${displaySize} ${units[idx]}`
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

export function mime_type_to_string(mime_type: string): string {
  if (mime_type === "application/pdf") {
    return "PDF"
  } else if (mime_type === "text/csv") {
    return "CSV"
  } else if (mime_type === "text/markdown") {
    return "Markdown"
  } else if (mime_type === "text/html") {
    return "HTML"
  } else if (mime_type === "text/plain") {
    return "Text"
  } else if (mime_type.startsWith("image/")) {
    return `Image (${mime_type.split("/")[1]})`
  } else if (mime_type.startsWith("text/")) {
    return `Text (${mime_type.split("/")[1]})`
  } else if (mime_type.startsWith("video/")) {
    return `Video (${mime_type.split("/")[1]})`
  } else if (mime_type.startsWith("audio/")) {
    return `Audio (${mime_type.split("/")[1]})`
  } else {
    return mime_type
  }
}

export function extractor_output_format(output_format: OutputFormat): string {
  switch (output_format) {
    case "text/plain":
      return "Text"
    case "text/markdown":
      return "Markdown"
    default: {
      // trigger a type error if there is a new output format, but don't handle it
      // in the switch
      const exhaustiveCheck: never = output_format
      return exhaustiveCheck
    }
  }
}

export function chunker_type_format(chunker_type: ChunkerType): string {
  switch (chunker_type) {
    case "fixed_window":
      return "Fixed Window"
    default: {
      // trigger a type error if there is a new chunker type, but don't handle it
      // in the switch
      const exhaustiveCheck: never = chunker_type
      return exhaustiveCheck
    }
  }
}

export function capitalize(str: string | undefined | null): string {
  if (!str) {
    return ""
  }
  return str.charAt(0).toUpperCase() + str.slice(1)
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
 * Converts ToolServerType to a human-readable string.
 * This function uses exhaustive case checking - if you add a new case to ToolType,
 * TypeScript will force you to handle it here.
 */
export function toolServerTypeToString(
  type: ToolServerType,
): string | undefined {
  switch (type) {
    case "remote_mcp":
      return "Remote MCP"
    case "local_mcp":
      return "Local MCP"
    case "kiln_task":
      return "Kiln Task"
    default: {
      // This ensures exhaustive checking - if you add a new case to StructuredOutputMode
      // and don't handle it above, TypeScript will error here
      const exhaustiveCheck: never = type
      console.warn(`Unhandled toolType: ${exhaustiveCheck}`)
      return undefined
    }
  }
}
