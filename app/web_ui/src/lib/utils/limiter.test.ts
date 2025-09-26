import { describe, it, expect } from "vitest"
import { createLimiter } from "./limiter"

describe("createLimiter", () => {
  describe("basic functionality", () => {
    it("should execute functions immediately when under limit", async () => {
      const run = createLimiter(2)
      const results: number[] = []

      const promises = [
        run(async () => {
          results.push(1)
          return 1
        }),
        run(async () => {
          results.push(2)
          return 2
        }),
      ]

      const values = await Promise.all(promises)
      expect(values).toEqual([1, 2])
      expect(results).toEqual([1, 2])
    })

    it("should queue functions when at limit", async () => {
      const run = createLimiter(1)
      const results: number[] = []

      // First function should execute immediately
      const firstPromise = run(async () => {
        results.push(1)
        await new Promise((resolve) => setTimeout(resolve, 50))
        return 1
      })

      // Second function should be queued
      const secondPromise = run(async () => {
        results.push(2)
        return 2
      })

      // Give first function time to start
      await new Promise((resolve) => setTimeout(resolve, 10))
      expect(results).toEqual([1])

      // Wait for both to complete
      const values = await Promise.all([firstPromise, secondPromise])
      expect(values).toEqual([1, 2])
      expect(results).toEqual([1, 2])
    })

    it("should process queue in FIFO order", async () => {
      const run = createLimiter(1)
      const executionOrder: number[] = []

      const promises = [
        run(async () => {
          executionOrder.push(1)
          await new Promise((resolve) => setTimeout(resolve, 30))
          return 1
        }),
        run(async () => {
          executionOrder.push(2)
          await new Promise((resolve) => setTimeout(resolve, 20))
          return 2
        }),
        run(async () => {
          executionOrder.push(3)
          await new Promise((resolve) => setTimeout(resolve, 10))
          return 3
        }),
      ]

      const values = await Promise.all(promises)
      expect(values).toEqual([1, 2, 3])
      expect(executionOrder).toEqual([1, 2, 3])
    })
  })

  describe("error handling", () => {
    it("should propagate errors correctly", async () => {
      const run = createLimiter(1)

      const errorPromise = run(async () => {
        throw new Error("Test error")
      })

      await expect(errorPromise).rejects.toThrow("Test error")
    })

    it("should continue processing queue after error", async () => {
      const run = createLimiter(1)
      const results: number[] = []

      const promises = [
        run(async () => {
          throw new Error("First error")
        }),
        run(async () => {
          results.push(2)
          return 2
        }),
        run(async () => {
          results.push(3)
          return 3
        }),
      ]

      await expect(promises[0]).rejects.toThrow("First error")
      const [value2, value3] = await Promise.all([promises[1], promises[2]])

      expect(value2).toBe(2)
      expect(value3).toBe(3)
      expect(results).toEqual([2, 3])
    })

    it("should handle mixed success and error cases", async () => {
      const run = createLimiter(2)
      const results: number[] = []

      const promises = [
        run(async () => {
          results.push(1)
          return 1
        }),
        run(async () => {
          throw new Error("Error in second")
        }),
        run(async () => {
          results.push(3)
          return 3
        }),
      ]

      const [value1, error2, value3] = await Promise.allSettled(promises)

      expect(value1).toEqual({ status: "fulfilled", value: 1 })
      expect(error2).toEqual({ status: "rejected", reason: expect.any(Error) })
      expect(value3).toEqual({ status: "fulfilled", value: 3 })
      expect(results).toEqual([1, 3])
    })
  })

  describe("concurrency limiting", () => {
    it("should respect concurrency limit", async () => {
      const run = createLimiter(2)
      const activeCount: number[] = []
      let maxConcurrent = 0

      const promises = Array.from({ length: 10 }, (_, i) =>
        run(async () => {
          activeCount.push(activeCount.length + 1)
          maxConcurrent = Math.max(maxConcurrent, activeCount.length)

          await new Promise((resolve) => setTimeout(resolve, 300))

          activeCount.pop()
          return i
        }),
      )

      await Promise.all(promises)
      expect(maxConcurrent).toBeLessThanOrEqual(2)
    })

    it("should handle rapid successive calls", async () => {
      const run = createLimiter(3)
      const results: number[] = []

      // Fire off many rapid calls
      const promises = Array.from({ length: 50 }, (_, i) =>
        run(async () => {
          results.push(i)
          await new Promise((resolve) => setTimeout(resolve, 10))
          return i
        }),
      )

      const values = await Promise.all(promises)
      expect(values).toEqual(Array.from({ length: 50 }, (_, i) => i))
      expect(results).toHaveLength(50)
    })
  })

  describe("return value preservation", () => {
    it("should preserve return values", async () => {
      const run = createLimiter(1)

      const result1 = await run(async () => "string result")
      const result2 = await run(async () => 42)
      const result3 = await run(async () => ({ key: "value" }))
      const result4 = await run(async () => [1, 2, 3])

      expect(result1).toBe("string result")
      expect(result2).toBe(42)
      expect(result3).toEqual({ key: "value" })
      expect(result4).toEqual([1, 2, 3])
    })

    it("should handle undefined return values", async () => {
      const run = createLimiter(1)

      const result = await run(async () => {
        // No return statement
      })

      expect(result).toBeUndefined()
    })
  })

  describe("edge cases", () => {
    it("should handle zero concurrency limit", async () => {
      const run = createLimiter(0)
      const results: number[] = []

      const promise1 = run(async () => {
        results.push(1)
        return 1
      })

      const promise2 = run(async () => {
        results.push(2)
        return 2
      })

      // Give time to ensure they're queued
      await new Promise((resolve) => setTimeout(resolve, 10))
      expect(results).toHaveLength(0)

      // With zero concurrency, the functions will never execute
      // This is expected behavior - they'll hang indefinitely
      // In practice, you'd never use zero concurrency
      expect(promise1).toBeInstanceOf(Promise)
      expect(promise2).toBeInstanceOf(Promise)
    }, 1000) // Short timeout since we expect this to hang

    it("should handle single concurrency", async () => {
      const run = createLimiter(1)
      const executionOrder: number[] = []

      const promises = Array.from({ length: 3 }, (_, i) =>
        run(async () => {
          executionOrder.push(i)
          await new Promise((resolve) => setTimeout(resolve, 20))
          return i
        }),
      )

      const values = await Promise.all(promises)
      expect(values).toEqual([0, 1, 2])
      expect(executionOrder).toEqual([0, 1, 2])
    })
  })

  describe("stress testing", () => {
    it("should handle many concurrent operations", async () => {
      const run = createLimiter(5)
      const results: number[] = []
      const errors: Error[] = []

      const operations = Array.from({ length: 50 }, (_, i) =>
        run(async () => {
          try {
            await new Promise((resolve) =>
              setTimeout(resolve, Math.random() * 20),
            )
            results.push(i)
            return i
          } catch (error) {
            errors.push(error as Error)
            throw error
          }
        }),
      )

      await Promise.allSettled(operations)

      expect(errors).toHaveLength(0)
      expect(results).toHaveLength(50)

      // Sort both arrays to compare them properly
      const sortedResults = results.sort((a, b) => a - b)
      const expectedResults = Array.from({ length: 50 }, (_, i) => i)
      expect(sortedResults).toEqual(expectedResults)
    })

    it("should maintain correct concurrency under load", async () => {
      const run = createLimiter(3)
      const activeCount: number[] = []
      let maxConcurrent = 0

      const operations = Array.from({ length: 20 }, (_, i) =>
        run(async () => {
          activeCount.push(activeCount.length + 1)
          maxConcurrent = Math.max(maxConcurrent, activeCount.length)

          await new Promise((resolve) =>
            setTimeout(resolve, Math.random() * 30),
          )

          activeCount.pop()
          return i
        }),
      )

      await Promise.all(operations)
      expect(maxConcurrent).toBeLessThanOrEqual(3)
    })
  })

  describe("real-world usage patterns", () => {
    it("should simulate API rate limiting", async () => {
      const run = createLimiter(2) // Max 2 concurrent API calls
      const apiCalls: number[] = []
      const responses: string[] = []

      // Simulate 6 API calls
      const promises = Array.from({ length: 6 }, (_, i) =>
        run(async () => {
          apiCalls.push(i)
          // Simulate API call delay
          await new Promise((resolve) => setTimeout(resolve, 100))
          const response = `Response ${i}`
          responses.push(response)
          return response
        }),
      )

      const results = await Promise.all(promises)

      expect(results).toHaveLength(6)
      expect(apiCalls).toHaveLength(6)
      expect(responses).toHaveLength(6)

      // Should have processed all calls
      expect(apiCalls.sort()).toEqual([0, 1, 2, 3, 4, 5])
    })

    it("should simulate file processing with concurrency limit", async () => {
      const run = createLimiter(3) // Max 3 concurrent file operations
      const processedFiles: string[] = []

      const fileNames = [
        "file1.txt",
        "file2.txt",
        "file3.txt",
        "file4.txt",
        "file5.txt",
      ]

      const promises = fileNames.map((fileName) =>
        run(async () => {
          // Simulate file processing
          await new Promise((resolve) => setTimeout(resolve, 50))
          processedFiles.push(fileName)
          return `Processed ${fileName}`
        }),
      )

      const results = await Promise.all(promises)

      expect(results).toHaveLength(5)
      expect(processedFiles).toHaveLength(5)
      expect(processedFiles.sort()).toEqual(fileNames.sort())
    })
  })
})
