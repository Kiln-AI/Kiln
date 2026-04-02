import { writable } from "svelte/store"

// Custom function to create a localStorage-backed store
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
    // Subscribe to changes and update localStorage
    store.subscribe((value) => {
      const stringified = JSON.stringify(value)
      // 1MB is a reasonable limit. Most browsers have a 5MB limit total for localStorage.
      if (stringified.length > 1 * 1024 * 1024) {
        console.error(
          "Skipping localStorage save for " + key + " as it's too large (>1MB)",
        )
      } else {
        localStorage.setItem(key, stringified)
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
      const stringified = JSON.stringify(value)
      if (stringified.length > 2 * 1024 * 1024) {
        console.error(
          "Skipping sessionStorage save for " +
            key +
            " as it's too large (>2MB)",
        )
      } else {
        sessionStorage.setItem(key, stringified)
      }
    })
  }

  return store
}
