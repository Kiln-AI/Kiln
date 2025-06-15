import { get } from "svelte/store"
import { indexedDBStore } from "./index_db_store"
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import type { Mock } from "vitest"

// Types for IndexedDB mocks
interface MockIDBRequest {
  result: unknown
  error: Error | null
  onsuccess: (() => void) | null
  onerror: ((event: Error) => void) | null
}

interface MockIDBOpenRequest extends MockIDBRequest {
  onupgradeneeded: (() => void) | null
}

interface MockIDBTransaction {
  objectStore: Mock<[string], MockIDBObjectStore>
  oncomplete: (() => void) | null
  onerror: ((event: Error) => void) | null
  error: Error | null
}

interface MockIDBObjectStore {
  get: Mock<[string], MockIDBRequest>
  put: Mock<[{ key: string; value: unknown }], void>
}

interface MockIDBDatabase {
  transaction: Mock<[string[], string], MockIDBTransaction>
  objectStoreNames: {
    contains: Mock<[string], boolean>
  }
  createObjectStore: Mock<[string, { keyPath: string }], MockIDBObjectStore>
}

// Mock IndexedDB for testing
let mockObjectStore: MockIDBObjectStore
let mockTransaction: MockIDBTransaction
let mockDatabase: MockIDBDatabase
let mockRequest: MockIDBOpenRequest
let mockIndexedDB: { open: Mock<[string, number], MockIDBOpenRequest> }

describe("indexedDBStore", () => {
  beforeEach(() => {
    // Reset all mocks
    vi.clearAllMocks()

    // Create fresh mock objects
    mockObjectStore = {
      get: vi.fn<[string], MockIDBRequest>(),
      put: vi.fn<[{ key: string; value: unknown }], void>(),
    }

    mockTransaction = {
      objectStore: vi.fn<[string], MockIDBObjectStore>(() => mockObjectStore),
      oncomplete: null,
      onerror: null,
      error: null,
    }

    mockDatabase = {
      transaction: vi.fn<[string[], string], MockIDBTransaction>(
        () => mockTransaction,
      ),
      objectStoreNames: {
        contains: vi.fn<[string], boolean>(() => false),
      },
      createObjectStore: vi.fn<
        [string, { keyPath: string }],
        MockIDBObjectStore
      >(() => mockObjectStore),
    }

    mockRequest = {
      result: mockDatabase,
      error: null,
      onsuccess: null,
      onerror: null,
      onupgradeneeded: null,
    }

    mockIndexedDB = {
      open: vi.fn<[string, number], MockIDBOpenRequest>(() => mockRequest),
    }

    // Reset mock behavior
    mockObjectStore.get.mockImplementation(() => ({
      result: null,
      error: null,
      onsuccess: null,
      onerror: null,
    }))

    mockObjectStore.put.mockImplementation(() => ({}))
    mockTransaction.objectStore.mockReturnValue(mockObjectStore)
    mockDatabase.transaction.mockReturnValue(mockTransaction)
    mockDatabase.objectStoreNames.contains.mockReturnValue(false)
    mockIndexedDB.open.mockReturnValue(mockRequest)

    // Mock browser environment
    vi.stubGlobal("window", {
      indexedDB: mockIndexedDB,
      localStorage: {
        getItem: vi.fn(),
        setItem: vi.fn(),
      },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  describe("in browser environment", () => {
    it("should create a store with initial value", () => {
      const store = indexedDBStore("test-key", "initial-value")
      expect(get(store)).toBe("initial-value")
    })

    it("should initialize IndexedDB on first access", async () => {
      indexedDBStore("test-key", "initial-value")

      // Wait a bit for async initialization
      await new Promise((resolve) => setTimeout(resolve, 0))

      expect(mockIndexedDB.open).toHaveBeenCalledWith("kiln_stores", 1)
    })

    it("should create object store on upgrade", () => {
      indexedDBStore("test-key", "initial-value")

      // Simulate onupgradeneeded event
      if (mockRequest.onupgradeneeded) {
        mockRequest.onupgradeneeded()
      }

      expect(mockDatabase.createObjectStore).toHaveBeenCalledWith(
        "key_value_store",
        { keyPath: "key" },
      )
    })

    it("should load stored value from IndexedDB", async () => {
      const storedValue = "stored-value"

      // Mock the entire flow step by step
      mockObjectStore.get.mockImplementation(() => {
        const request: MockIDBRequest = {
          result: { key: "test-key", value: storedValue },
          error: null,
          onsuccess: null,
          onerror: null,
        }
        // Simulate immediate async success
        process.nextTick(() => {
          if (request.onsuccess) request.onsuccess()
        })
        return request
      })

      const storeInstance = indexedDBStore("test-key", "initial-value")

      // Trigger the DB initialization success which will trigger getValue
      process.nextTick(() => {
        if (mockRequest.onsuccess) {
          mockRequest.onsuccess()
        }
      })

      // Wait for all async operations to complete
      await new Promise((resolve) => setTimeout(resolve, 10))

      expect(get(storeInstance)).toBe(storedValue)
    })

    it("should handle IndexedDB initialization errors gracefully", async () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})

      const store = indexedDBStore("test-key", "initial-value")

      // Simulate DB initialization error
      if (mockRequest.onerror) {
        mockRequest.error = new Error("DB failed to open")
        mockRequest.onerror(mockRequest.error)
      }

      // Wait for error handling
      await new Promise((resolve) => setTimeout(resolve, 10))

      // Store should still work with initial value
      expect(get(store)).toBe("initial-value")
      expect(consoleSpy).toHaveBeenCalledWith(
        "Failed to open IndexedDB:",
        expect.any(Error),
      )

      consoleSpy.mockRestore()
    })

    it("should handle get operation errors gracefully", async () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})

      // Mock get to throw an error
      mockObjectStore.get.mockImplementation(() => {
        const request: MockIDBRequest = {
          result: null,
          error: new Error("Get failed"),
          onsuccess: null,
          onerror: null,
        }
        process.nextTick(() => {
          if (request.onerror) request.onerror(request.error!)
        })
        return request
      })

      const storeInstance = indexedDBStore("test-key", "initial-value")

      // Trigger DB initialization success which will then allow getValue to proceed
      process.nextTick(() => {
        if (mockRequest.onsuccess) {
          mockRequest.onsuccess()
        }
      })

      await new Promise((resolve) => setTimeout(resolve, 10))

      // Should keep initial value on error
      expect(get(storeInstance)).toBe("initial-value")
      expect(consoleSpy).toHaveBeenCalledWith(
        "Failed to load initial value from IndexedDB:",
        expect.any(Error),
      )

      consoleSpy.mockRestore()
    })

    it("should handle null stored values correctly", async () => {
      // Mock get operation returning null
      const mockGetRequest: MockIDBRequest = {
        result: null,
        error: null,
        onsuccess: null,
        onerror: null,
      }

      mockObjectStore.get.mockReturnValue(mockGetRequest)

      const store = indexedDBStore("test-key", "initial-value")

      // Simulate successful DB initialization and get
      setTimeout(() => {
        if (mockRequest.onsuccess) {
          mockRequest.onsuccess()
          setTimeout(() => {
            if (mockGetRequest.onsuccess) {
              mockGetRequest.onsuccess()
            }
          }, 0)
        }
      }, 0)

      await new Promise((resolve) => setTimeout(resolve, 10))

      // Should keep initial value when no stored value found
      expect(get(store)).toBe("initial-value")
    })

    it("should create separate database connections for each store", async () => {
      // Clear any previous calls
      vi.clearAllMocks()

      // First store creation
      indexedDBStore("key1", "value1")
      await new Promise((resolve) => setTimeout(resolve, 10))

      // Second store creation
      indexedDBStore("key2", "value2")
      await new Promise((resolve) => setTimeout(resolve, 10))

      // Each store should create its own DB connection (db variable is scoped per function call)
      expect(mockIndexedDB.open).toHaveBeenCalledTimes(2)
    })
  })

  describe("in non-browser environment", () => {
    beforeEach(() => {
      // Remove window object to simulate non-browser environment
      vi.unstubAllGlobals()
    })

    it("should work without IndexedDB", () => {
      const store = indexedDBStore("test-key", "initial-value")
      expect(get(store)).toBe("initial-value")

      // Should not attempt to use IndexedDB
      expect(mockIndexedDB.open).not.toHaveBeenCalled()
    })

    it("should still be reactive without IndexedDB", () => {
      const store = indexedDBStore("test-key", "initial-value")

      store.set("new-value")
      expect(get(store)).toBe("new-value")
    })
  })

  describe("edge cases", () => {
    it("should handle IndexedDB not being available", () => {
      // Mock browser environment without IndexedDB
      vi.stubGlobal("window", {
        localStorage: {
          getItem: vi.fn(),
          setItem: vi.fn(),
        },
      })

      const store = indexedDBStore("test-key", "initial-value")
      expect(get(store)).toBe("initial-value")

      // Should not crash when IndexedDB is not available
      store.set("new-value")
      expect(get(store)).toBe("new-value")
    })
  })
})
