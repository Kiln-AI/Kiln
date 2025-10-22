export function get_splits_from_url_param(splitsParam: string | null) {
  if (!splitsParam) return {}

  try {
    const splitMap: Record<string, number> = {}
    const pairs = splitsParam.split(",")

    for (const pair of pairs) {
      const [name, value] = pair.split(":").map((s) => s.trim())
      const numValue = parseFloat(value)
      if (isNaN(numValue) || numValue < 0 || numValue > 1) {
        throw new Error("Invalid split value")
      }
      splitMap[name] = numValue
    }

    // Validate that splits sum to 1
    const total = Object.values(splitMap).reduce((sum, val) => sum + val, 0)
    if (Math.abs(total - 1) > 0.001) {
      throw new Error("Split values must sum to 1")
    }

    return splitMap
  } catch (e) {
    console.warn("Invalid splits parameter, using default", e)
    return {}
  }
}

export function encode_splits_for_url(splits: Record<string, number>) {
  return Object.entries(splits)
    .map(([name, value]) => `${name}:${value}`)
    .join(",")
}

export function get_splits_subtitle(splits: Record<string, number>) {
  if (Object.keys(splits).length === 0) return undefined
  return `Added data will be assigned the following tags: ${Object.entries(
    splits,
  )
    .map(([name, value]) => `${Math.round(value * 100)}% ${name}`)
    .join(", ")}`
}
