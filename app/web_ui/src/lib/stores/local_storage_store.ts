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
    store.subscribe((value) => {
      try {
        localStorage.setItem(key, JSON.stringify(value))
      } catch {
        console.error("Failed to save to localStorage for key: " + key)
        localStorage.removeItem(key)
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
        sessionStorage.removeItem(key)
      }
    })
  }

  return store
}
