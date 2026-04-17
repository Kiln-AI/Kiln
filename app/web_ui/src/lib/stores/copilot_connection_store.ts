import { writable } from "svelte/store"
import { browser } from "$app/environment"
import { checkKilnCopilotAvailable } from "$lib/utils/copilot_utils"

const STORAGE_KEY = "kiln_copilot_connected"

export const kilnCopilotConnected = writable<boolean | null>(null)

let initialized = false

function parseBool(raw: string | null): boolean | null {
  if (raw === "true") return true
  if (raw === "false") return false
  return null
}

function readCached(): boolean | null {
  if (!browser) return null
  try {
    const session = parseBool(sessionStorage.getItem(STORAGE_KEY))
    if (session !== null) return session
    const local = parseBool(localStorage.getItem(STORAGE_KEY))
    if (local !== null) return local
  } catch {
    // storage unavailable
  }
  return null
}

function persistToStorage(connected: boolean): void {
  if (!browser) return
  try {
    const value = String(connected)
    sessionStorage.setItem(STORAGE_KEY, value)
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    // storage unavailable
  }
}

export async function refreshCopilotConnectionStatus(): Promise<void> {
  try {
    const connected = await checkKilnCopilotAvailable()
    kilnCopilotConnected.set(connected)
    persistToStorage(connected)
  } catch {
    kilnCopilotConnected.set(false)
    persistToStorage(false)
  }
}

export function setCopilotConnected(connected: boolean): void {
  kilnCopilotConnected.set(connected)
  persistToStorage(connected)
}

export function initCopilotConnectionStore(): void {
  if (!browser || initialized) return
  initialized = true

  const cached = readCached()
  if (cached !== null) {
    kilnCopilotConnected.set(cached)
  }

  refreshCopilotConnectionStatus()

  window.addEventListener("storage", (e: StorageEvent) => {
    if (e.key === STORAGE_KEY && e.newValue !== null) {
      kilnCopilotConnected.set(e.newValue === "true")
    }
  })

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      refreshCopilotConnectionStatus()
    }
  })
}
