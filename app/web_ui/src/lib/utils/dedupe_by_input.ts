// Return a new array with items whose `input` string has already been seen
// removed, preserving order. Used to de-duplicate identical synthetic input
// previews so the review table shows only unique examples (1..N, not always N).
export function dedupe_by_input<T extends { input: string }>(items: T[]): T[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    if (seen.has(item.input)) return false
    seen.add(item.input)
    return true
  })
}
