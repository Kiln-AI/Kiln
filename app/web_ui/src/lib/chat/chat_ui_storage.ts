const STORAGE_KEY = "chat_bar_expanded"
const WIDTH_STORAGE_KEY = "chat_bar_width"

export function getChatBarExpanded(): boolean {
  try {
    const sessionValue = sessionStorage.getItem(STORAGE_KEY)
    if (sessionValue !== null) {
      return sessionValue === "true"
    }
    const localValue = localStorage.getItem(STORAGE_KEY)
    if (localValue !== null) {
      return localValue === "true"
    }
  } catch {
    // Storage may be unavailable (e.g. private browsing)
  }
  return true
}

export function setChatBarExpanded(expanded: boolean): void {
  try {
    const value = expanded ? "true" : "false"
    sessionStorage.setItem(STORAGE_KEY, value)
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    // Storage may be unavailable
  }
}

export function getChatBarWidth(): number | null {
  try {
    const value = localStorage.getItem(WIDTH_STORAGE_KEY)
    if (value !== null) {
      const parsed = Number(value)
      if (!isNaN(parsed) && parsed > 0) {
        return parsed
      }
    }
  } catch {
    // Storage may be unavailable
  }
  return null
}

export function setChatBarWidth(width: number): void {
  try {
    localStorage.setItem(WIDTH_STORAGE_KEY, String(width))
  } catch {
    // Storage may be unavailable
  }
}
