export function isMacOS(): boolean {
  return (
    typeof window !== "undefined" &&
    navigator.platform.toUpperCase().indexOf("MAC") >= 0
  )
}
