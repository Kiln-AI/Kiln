import { writable } from "svelte/store"

// Custom function to create an IndexedDB-backed store
export function indexedDBStore<T>(key: string, initialValue: T) {
  // Check if IndexedDB is available
  const isBrowser = typeof window !== "undefined" && window.indexedDB

  const store = writable(initialValue)
  const DB_NAME = "kiln_stores"
  const STORE_NAME = "key_value_store"
  const DB_VERSION = 1

  if (isBrowser) {
    let db: IDBDatabase | null = null
    let isInitialized = false

    // Initialize IndexedDB
    const initDB = (): Promise<IDBDatabase> => {
      return new Promise((resolve, reject) => {
        if (db) {
          resolve(db)
          return
        }

        const request = window.indexedDB.open(DB_NAME, DB_VERSION)

        request.onerror = () => {
          console.error("Failed to open IndexedDB:", request.error)
          reject(request.error)
        }

        request.onsuccess = () => {
          db = request.result
          resolve(db)
        }

        request.onupgradeneeded = () => {
          const database = request.result
          if (!database.objectStoreNames.contains(STORE_NAME)) {
            database.createObjectStore(STORE_NAME, { keyPath: "key" })
          }
        }
      })
    }

    // Get value from IndexedDB
    const getValue = async (): Promise<T | null> => {
      try {
        const database = await initDB()
        const transaction = database.transaction([STORE_NAME], "readonly")
        const objectStore = transaction.objectStore(STORE_NAME)
        const request = objectStore.get(key)

        return new Promise((resolve, reject) => {
          request.onsuccess = () => {
            const result = request.result
            resolve(result ? result.value : null)
          }
          request.onerror = () => reject(request.error)
        })
      } catch (error) {
        console.error("Failed to get value from IndexedDB:", error)
        return null
      }
    }

    // Set value in IndexedDB
    const setValue = async (value: T): Promise<void> => {
      let database: IDBDatabase
      try {
        database = await initDB()
      } catch (error) {
        console.error(
          `Failed to initialize DB for setValue (key: ${key}):`,
          error,
        )
        throw error
      }

      try {
        const transaction = database.transaction([STORE_NAME], "readwrite")
        const objectStore = transaction.objectStore(STORE_NAME)
        objectStore.put({ key, value })

        return new Promise((resolve, reject) => {
          transaction.oncomplete = () => resolve()
          transaction.onerror = () => {
            reject(transaction.error)
          }
        })
      } catch (error) {
        console.error(
          `Error setting up transaction/put in setValue (key: ${key}):`,
          error,
        )
        throw error
      }
    }

    // Load initial value from IndexedDB
    getValue()
      .then((storedValue) => {
        if (storedValue !== null) {
          store.set(storedValue)
        }
      })
      .catch((error) => {
        console.error("Failed to load initial value from IndexedDB:", error)
      })
      .finally(() => {
        isInitialized = true
      })

    // Subscribe to changes and update IndexedDB
    store.subscribe((value) => {
      if (isInitialized) {
        setValue(value).catch((error) => {
          console.error("Failed to update IndexedDB:", error)
        })
      }
    })
  }

  return store
}
