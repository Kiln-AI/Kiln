export function arrays_equal<T>(a: T[], b: T[]): boolean {
  return a.length === b.length && a.every((val, index) => val === b[index])
}

export function sets_equal<T>(a: Set<T>, b: Set<T>): boolean {
  if (a.size !== b.size) return false
  for (const item of a) {
    if (!b.has(item)) return false
  }
  return true
}
