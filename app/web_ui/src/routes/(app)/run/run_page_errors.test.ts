import { describe, it, expect } from "vitest"
import { looks_like_error_with_trace } from "./error_with_trace_detection"

describe("looks_like_error_with_trace (type guard)", () => {
  it("returns true for an ErrorWithTrace body with trace present", () => {
    const body = {
      message: "Rate limit exceeded. Wait a moment and try again.",
      error_type: "RateLimitError",
      trace: [
        { role: "system", content: "You are a helpful assistant." },
        { role: "user", content: "hello" },
      ],
    }
    expect(looks_like_error_with_trace(body)).toBe(true)
  })

  it("returns true when trace is null (failure before any messages built)", () => {
    const body = {
      message: "Could not connect to the model provider.",
      error_type: "APIConnectionError",
      trace: null,
    }
    expect(looks_like_error_with_trace(body)).toBe(true)
  })

  it("returns true when trace is omitted from the body", () => {
    const body = {
      message: "Authentication failed.",
      error_type: "AuthenticationError",
    }
    expect(looks_like_error_with_trace(body)).toBe(true)
  })

  it("returns true when trace is an empty array", () => {
    const body = {
      message: "Something went wrong.",
      error_type: "RuntimeError",
      trace: [],
    }
    expect(looks_like_error_with_trace(body)).toBe(true)
  })

  it("returns false for a plain HTTPException detail body", () => {
    const body = { detail: "Task not found." }
    expect(looks_like_error_with_trace(body)).toBe(false)
  })

  it("returns false for an HTTPException with message but no error_type", () => {
    const body = { message: "bad input", raw_error: "something" }
    expect(looks_like_error_with_trace(body)).toBe(false)
  })

  it("returns false for null body", () => {
    expect(looks_like_error_with_trace(null)).toBe(false)
  })

  it("returns false for undefined body", () => {
    expect(looks_like_error_with_trace(undefined)).toBe(false)
  })

  it("returns false for a string body (e.g. text/plain 500 page)", () => {
    expect(looks_like_error_with_trace("Internal Server Error")).toBe(false)
  })

  it("returns false for a numeric body", () => {
    expect(looks_like_error_with_trace(500)).toBe(false)
  })

  it("returns false when message is not a string", () => {
    const body = { message: 42, error_type: "RuntimeError", trace: null }
    expect(looks_like_error_with_trace(body)).toBe(false)
  })

  it("returns false when error_type is not a string", () => {
    const body = { message: "bad", error_type: 123, trace: null }
    expect(looks_like_error_with_trace(body)).toBe(false)
  })

  it("returns false when trace is a non-array object", () => {
    const body = {
      message: "bad",
      error_type: "RuntimeError",
      trace: { not: "an array" },
    }
    expect(looks_like_error_with_trace(body)).toBe(false)
  })

  it("returns false when trace is a string", () => {
    const body = {
      message: "bad",
      error_type: "RuntimeError",
      trace: "not an array",
    }
    expect(looks_like_error_with_trace(body)).toBe(false)
  })
})
