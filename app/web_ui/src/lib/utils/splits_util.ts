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

export type WeightedSplit = {
  tag: string
  weight: number
}

/**
 * Turn relative weights into split fractions that sum to exactly 1.
 *
 * Callers have a table of base weights per split (train/val/test/golden), but only some of
 * those splits exist on a given eval. Dropping the absent ones leaves weights that no longer
 * total 100, so the survivors are rescaled — and the result has to land on integer percents,
 * because splits are rendered as `Math.round(value * 100)%` and are rejected downstream
 * (`get_splits_from_url_param`) unless they sum to 1.
 *
 * Rounding each share on its own does not sum to 100 — 25 and 10 rescale to 71.43 and 28.57,
 * which round to 71 and 29 only if the second one rounds up while the first rounds down. So
 * the leftover points are handed out by largest remainder: floor every share, then give the
 * remaining points to the largest fractional parts, ties broken by the caller's order. That
 * makes the order of `entries` meaningful — pass splits in the priority they should win ties.
 *
 * Entries repeating a tag are folded into one (weights summed) so the returned record keeps
 * its total at 1 instead of losing a share to key collision. Non-positive weights are dropped.
 */
export function allocate_splits(
  entries: WeightedSplit[],
): Record<string, number> {
  const merged: WeightedSplit[] = []
  for (const entry of entries) {
    if (!entry.tag || entry.weight <= 0) {
      continue
    }
    const existing = merged.find((m) => m.tag === entry.tag)
    if (existing) {
      existing.weight += entry.weight
    } else {
      merged.push({ tag: entry.tag, weight: entry.weight })
    }
  }

  const total_weight = merged.reduce((sum, entry) => sum + entry.weight, 0)
  if (total_weight <= 0) {
    return {}
  }

  const shares = merged.map((entry, index) => {
    const exact = (entry.weight * 100) / total_weight
    const percent = Math.floor(exact)
    return { tag: entry.tag, index, percent, remainder: exact - percent }
  })

  let leftover = 100 - shares.reduce((sum, share) => sum + share.percent, 0)
  const by_remainder = [...shares].sort(
    (a, b) => b.remainder - a.remainder || a.index - b.index,
  )
  for (const share of by_remainder) {
    if (leftover <= 0) {
      break
    }
    share.percent += 1
    leftover -= 1
  }

  const splits: Record<string, number> = {}
  for (const share of shares) {
    splits[share.tag] = share.percent / 100
  }
  return splits
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

export function splits_equal(
  a: Record<string, number>,
  b: Record<string, number>,
): boolean {
  const keysA = Object.keys(a).sort()
  const keysB = Object.keys(b).sort()
  if (keysA.length !== keysB.length) return false
  for (let i = 0; i < keysA.length; i++) {
    if (keysA[i] !== keysB[i] || a[keysA[i]] !== b[keysA[i]]) return false
  }
  return true
}
