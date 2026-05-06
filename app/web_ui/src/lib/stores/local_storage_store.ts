import { writable } from "svelte/store"

// Creates a localStorage-backed Svelte store. The internal subscription that
// persists values is never cleaned up, so callers must be module-level
// singletons (not created inside components or loops).
export function localStorageStore<T>(key: string, initialValue: T) {
  // Check if localStorage is available
  const isBrowser = typeof window !== "undefined" && window.localStorage

  let storedValue: T | null = null
  if (isBrowser) {
    try {
      storedValue = JSON.parse(localStorage.getItem(key) || "null")
    } catch {
      storedValue = null
    }
  }
  const store = writable(storedValue !== null ? storedValue : initialValue)

  if (isBrowser) {
    store.subscribe((value) => {
      try {
        localStorage.setItem(key, JSON.stringify(value))
      } catch {
        console.error("Failed to save to localStorage for key: " + key)
        try {
          localStorage.removeItem(key)
        } catch {
          // removeItem may also fail in degraded environments (e.g. Node 25+
          // exposes a localStorage global that is non-functional without a
          // backing file)
        }
      }
    })
  }

  return store
}

export function sessionStorageStore<T>(key: string, initialValue: T) {
  const isBrowser = typeof window !== "undefined" && window.sessionStorage

  let storedValue: T | null = null
  if (isBrowser) {
    try {
      storedValue = JSON.parse(sessionStorage.getItem(key) || "null")
    } catch {
      storedValue = null
    }
  }
  const store = writable(storedValue !== null ? storedValue : initialValue)

  if (isBrowser) {
    store.subscribe((value) => {
      try {
        sessionStorage.setItem(key, JSON.stringify(value))
      } catch {
        console.error("Failed to save to sessionStorage for key: " + key)
        try {
          sessionStorage.removeItem(key)
        } catch {
          // removeItem may also fail in degraded environments
        }
      }
    })
  }

  return store
}
