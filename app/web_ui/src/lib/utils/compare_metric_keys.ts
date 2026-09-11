// The row keys of the comparison table's usage section, shared by the compare page
// that builds the table and the radar chart that turns the same rows into axes.
// Renaming a key in one place without the other would silently drop an axis, so
// there is one definition of each.

// Section id of the usage rows. Not an eval, so the page skips it wherever it looks
// up eval data, and the chart scores its rows by position rather than by range.
export const COST_SECTION_ID = "kiln_cost_section"

const USAGE_KEY_PREFIX = "cost::"

export const INPUT_TOKENS_KEY = `${USAGE_KEY_PREFIX}mean_input_tokens`
export const OUTPUT_TOKENS_KEY = `${USAGE_KEY_PREFIX}mean_output_tokens`
export const TOTAL_TOKENS_KEY = `${USAGE_KEY_PREFIX}mean_total_tokens`
export const COST_KEY = `${USAGE_KEY_PREFIX}mean_cost`
export const LATENCY_KEY = `${USAGE_KEY_PREFIX}mean_total_llm_latency_ms`

export type UsageMetric = {
  key: string
  // Name in the comparison table, above the raw quantity
  label: string
  // Name on the radar axis, where a bigger value means less of the quantity
  axisLabel: string
}

// In table order, which is also axis order.
export const USAGE_METRICS: UsageMetric[] = [
  {
    key: INPUT_TOKENS_KEY,
    label: "Input Tokens",
    axisLabel: "Input Token Efficiency",
  },
  {
    key: OUTPUT_TOKENS_KEY,
    label: "Output Tokens",
    axisLabel: "Output Token Efficiency",
  },
  {
    key: TOTAL_TOKENS_KEY,
    label: "Total Tokens",
    axisLabel: "Token Efficiency",
  },
  { key: COST_KEY, label: "Cost (USD)", axisLabel: "Cost Efficiency" },
  { key: LATENCY_KEY, label: "Latency", axisLabel: "Speed" },
]

// Usage rows carry a lower-is-better raw quantity, unlike eval scores.
export function isUsageMetricKey(key: string): boolean {
  return key.startsWith(USAGE_KEY_PREFIX)
}
