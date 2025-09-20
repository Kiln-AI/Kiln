import { describe, it, expect, beforeEach } from "vitest"
import { Semaphore } from "./semaphore"

describe("Semaphore", () => {
  let semaphore: Semaphore

  beforeEach(() => {
    semaphore = new Semaphore(2) // Start with capacity of 2 for most tests
  })

  describe("basic functionality", () => {
    it("should allow immediate acquisition when capacity is available", async () => {
      await semaphore.acquire()
      // Should not throw or hang
    })

    it("should allow multiple acquisitions up to capacity", async () => {
      await semaphore.acquire()
      await semaphore.acquire()
      // Both should succeed immediately
    })

    it("should release capacity when release is called", async () => {
      await semaphore.acquire()
      await semaphore.acquire()

      semaphore.release()

      // Should now be able to acquire again
      await semaphore.acquire()
    })

    it("should handle single capacity semaphore", async () => {
      const singleSemaphore = new Semaphore(1)

      await singleSemaphore.acquire()

      // Second acquire should be queued
      let secondAcquired = false
      const secondPromise = singleSemaphore.acquire().then(() => {
        secondAcquired = true
      })

      // Give it a moment to ensure it's queued
      await new Promise((resolve) => setTimeout(resolve, 10))
      expect(secondAcquired).toBe(false)

      singleSemaphore.release()
      await secondPromise
      expect(secondAcquired).toBe(true)
    })
  })

  describe("concurrency limiting", () => {
    it("should queue acquisitions when at capacity", async () => {
      // Fill up the semaphore
      await semaphore.acquire()
      await semaphore.acquire()

      let thirdAcquired = false
      const thirdPromise = semaphore.acquire().then(() => {
        thirdAcquired = true
      })

      // Give it a moment to ensure it's queued
      await new Promise((resolve) => setTimeout(resolve, 10))
      expect(thirdAcquired).toBe(false)

      // Release one slot
      semaphore.release()
      await thirdPromise
      expect(thirdAcquired).toBe(true)
    })

    it("should process queue in FIFO order", async () => {
      // Fill up the semaphore
      await semaphore.acquire()
      await semaphore.acquire()

      const acquiredOrder: number[] = []

      // Queue multiple acquisitions
      const promises = [
        semaphore.acquire().then(() => acquiredOrder.push(1)),
        semaphore.acquire().then(() => acquiredOrder.push(2)),
        semaphore.acquire().then(() => acquiredOrder.push(3)),
        semaphore.acquire().then(() => acquiredOrder.push(4)),
      ]

      // Give them time to queue
      await new Promise((resolve) => setTimeout(resolve, 10))

      // Release slots one by one
      semaphore.release()
      await new Promise((resolve) => setTimeout(resolve, 10))

      semaphore.release()
      await new Promise((resolve) => setTimeout(resolve, 10))

      semaphore.release()
      await new Promise((resolve) => setTimeout(resolve, 10))

      semaphore.release()
      await new Promise((resolve) => setTimeout(resolve, 10))

      await Promise.all(promises)

      expect(acquiredOrder).toEqual([1, 2, 3, 4])
    })

    it("should handle multiple releases correctly", () => {
      const singleSemaphore = new Semaphore(1)

      // Acquire and release multiple times
      singleSemaphore.acquire()
      singleSemaphore.release()
      singleSemaphore.acquire()
      singleSemaphore.release()

      // Should be able to acquire again
      expect(singleSemaphore.acquire()).resolves.toBeUndefined()
    })
  })

  describe("throttling scenario simulation", () => {
    it("should simulate RAG progress store throttling behavior", async () => {
      // Simulate the sseSlots semaphore with capacity 5
      const sseSlots = new Semaphore(5)

      const results: number[] = []
      const startTime = Date.now()

      // Simulate 10 concurrent operations (more than the semaphore capacity)
      const operations = Array.from({ length: 10 }, (_, i) =>
        (async () => {
          await sseSlots.acquire()
          try {
            // Simulate some async work (like creating EventSource)
            await new Promise((resolve) => setTimeout(resolve, 50))
            results.push(i)
          } finally {
            sseSlots.release()
          }
        })(),
      )

      await Promise.all(operations)

      const endTime = Date.now()
      const duration = endTime - startTime

      // Should have processed all 10 operations
      expect(results).toHaveLength(10)
      expect(results.sort()).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])

      // Should have taken some time due to throttling
      // With capacity 5 and 10 operations, should take at least 100ms (2 batches of 50ms each)
      expect(duration).toBeGreaterThanOrEqual(100)
    })

    it("should handle rapid acquire/release cycles", async () => {
      const rapidSemaphore = new Semaphore(3)
      const results: number[] = []

      // Simulate rapid operations
      const operations = Array.from({ length: 20 }, (_, i) =>
        (async () => {
          await rapidSemaphore.acquire()
          try {
            // Very short work
            await new Promise((resolve) => setTimeout(resolve, 1))
            results.push(i)
          } finally {
            rapidSemaphore.release()
          }
        })(),
      )

      await Promise.all(operations)

      expect(results).toHaveLength(20)
      // Results should contain all numbers 0-19, but order may vary due to concurrency
      const sortedResults = results.sort((a, b) => a - b)
      expect(sortedResults).toEqual(Array.from({ length: 20 }, (_, i) => i))
    })

    it("should maintain correct capacity tracking", async () => {
      const capacity = 3
      const testSemaphore = new Semaphore(capacity)

      // Fill up to capacity
      await testSemaphore.acquire()
      await testSemaphore.acquire()
      await testSemaphore.acquire()

      // Next acquire should be queued
      let queuedAcquired = false
      const queuedPromise = testSemaphore.acquire().then(() => {
        queuedAcquired = true
      })

      await new Promise((resolve) => setTimeout(resolve, 10))
      expect(queuedAcquired).toBe(false)

      // Release one
      testSemaphore.release()
      await queuedPromise
      expect(queuedAcquired).toBe(true)
    })
  })

  describe("edge cases", () => {
    it("should handle zero capacity semaphore", async () => {
      const zeroSemaphore = new Semaphore(0)

      // Any acquire should be queued
      let acquired = false
      const promise = zeroSemaphore.acquire().then(() => {
        acquired = true
      })

      await new Promise((resolve) => setTimeout(resolve, 10))
      expect(acquired).toBe(false)

      // Release should allow acquisition
      zeroSemaphore.release()
      await promise
      expect(acquired).toBe(true)
    })

    it("should handle release when no one is waiting", () => {
      const semaphore = new Semaphore(2)

      // Release when no one is waiting should increase capacity
      semaphore.release()
      semaphore.release()

      // Should now be able to acquire 4 times
      expect(semaphore.acquire()).resolves.toBeUndefined()
      expect(semaphore.acquire()).resolves.toBeUndefined()
      expect(semaphore.acquire()).resolves.toBeUndefined()
      expect(semaphore.acquire()).resolves.toBeUndefined()
    })

    it("should handle multiple releases without acquisitions", () => {
      const semaphore = new Semaphore(1)

      // Multiple releases without acquisitions
      semaphore.release()
      semaphore.release()
      semaphore.release()

      // Should be able to acquire multiple times now
      expect(semaphore.acquire()).resolves.toBeUndefined()
      expect(semaphore.acquire()).resolves.toBeUndefined()
      expect(semaphore.acquire()).resolves.toBeUndefined()
    })
  })

  describe("concurrent stress test", () => {
    it("should handle many concurrent operations correctly", async () => {
      const stressSemaphore = new Semaphore(5)
      const results: number[] = []
      const errors: Error[] = []

      // Create 100 concurrent operations
      const operations = Array.from({ length: 100 }, (_, i) =>
        (async () => {
          try {
            await stressSemaphore.acquire()
            try {
              // Simulate some work
              await new Promise((resolve) =>
                setTimeout(resolve, Math.random() * 10),
              )
              results.push(i)
            } finally {
              stressSemaphore.release()
            }
          } catch (error) {
            errors.push(error as Error)
          }
        })(),
      )

      await Promise.all(operations)

      expect(errors).toHaveLength(0)
      expect(results).toHaveLength(100)
      // Results should contain all numbers 0-99, but order may vary due to concurrency
      const sortedResults = results.sort((a, b) => a - b)
      expect(sortedResults).toEqual(Array.from({ length: 100 }, (_, i) => i))
    })
  })
})
