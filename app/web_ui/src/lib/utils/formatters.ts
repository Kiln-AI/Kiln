import { type EvalConfigType } from "$lib/types"

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
      return "Reasoning"
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
