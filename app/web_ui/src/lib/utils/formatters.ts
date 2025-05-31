import { type EvalConfigType } from "$lib/types"
import { _ } from "svelte-i18n"
import { get } from "svelte/store"

export function formatDate(dateString: string | undefined): string {
  if (!dateString) {
    return get(_)("formatters.unknown")
  }
  const date = new Date(dateString)
  const time_ago = Date.now() - date.getTime()

  if (time_ago < 1000 * 60) {
    return get(_)("formatters.just_now")
  }
  if (time_ago < 1000 * 60 * 2) {
    return get(_)("formatters.one_minute_ago")
  }
  if (time_ago < 1000 * 60 * 60) {
    return `${Math.floor(time_ago / (1000 * 60))} ${get(_)("formatters.minutes_ago")}`
  }
  if (date.toDateString() === new Date().toDateString()) {
    return (
      date.toLocaleString(undefined, {
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      }) +
      " " +
      get(_)("formatters.today")
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
      g_eval: get(_)("formatters.eval_config.g_eval"),
      llm_as_judge: get(_)("formatters.eval_config.llm_as_judge"),
    }[eval_config_type] || eval_config_type
  )
}

export function data_strategy_name(data_strategy: string): string {
  switch (data_strategy) {
    case "final_only":
      return get(_)("formatters.data_strategy.standard")
    case "final_and_intermediate":
      return get(_)("formatters.data_strategy.reasoning")
    default:
      return data_strategy
  }
}

export function rating_name(rating_type: string): string {
  switch (rating_type) {
    case "five_star":
      return get(_)("formatters.rating.five_star")
    case "pass_fail":
      return get(_)("formatters.rating.pass_fail")
    case "pass_fail_critical":
      return get(_)("formatters.rating.pass_fail_critical")
    default:
      return rating_type
  }
}
