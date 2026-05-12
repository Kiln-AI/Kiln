import hljs from "highlight.js/lib/core"
import json from "highlight.js/lib/languages/json"

hljs.registerLanguage("json", json)

export type ExpandedContent = {
  value: string
  isJson: boolean
}

export function formatExpandedContent(data: string): ExpandedContent {
  try {
    const json_data = JSON.parse(data)
    if (typeof json_data !== "string") {
      const formatted = JSON.stringify(json_data, null, 2)
      const highlighted = hljs.highlight(formatted, {
        language: "json",
      }).value
      return { value: highlighted, isJson: true }
    }
  } catch (_) {
    // Not valid JSON, return as plain text
  }
  return { value: data, isJson: false }
}
