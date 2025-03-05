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
