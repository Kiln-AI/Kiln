const STORAGE_KEY = "chat_bar_expanded"

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
