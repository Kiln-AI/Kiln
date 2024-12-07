export function formatDate(dateString: string | undefined): string {
  if (!dateString) {
    return "Unknown"
  }
  const date = new Date(dateString)
  const currentYear = new Date().getFullYear()
  const options: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }

  if (date.getFullYear() !== currentYear) {
    options.year = "numeric"
  }

  return date.toLocaleString("en-US", options)
}
