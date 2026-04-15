import { describe, it, expect } from "vitest"
import { looks_like_error_with_trace } from "./error_with_trace_detection"

// Phase 4 wires the run page to distinguish three fetch outcomes:
//   1. 500 with an ErrorWithTrace body -> render <ErrorWithTrace>
//   2. 500 (or 4xx) with a plain HTTPException body -> FormContainer fallback
//   3. Network failure / non-JSON body -> FormContainer fallback
// In all three cases the submit button re-enables because `submitting = false`
// lives inside a `finally` block.
//
// The single decision point driving (1) vs (2)+(3) on the run page is
// `looks_like_error_with_trace(fetch_error)`. `fetch_error` is whatever
// openapi-fetch parsed out of the response body (JSON object, string fallback,
// or {} for empty bodies per `openapi-fetch/dist/index.js`). These tests feed
// each scenario's realistic `fetch_error` shape into the type guard and assert
// the routing decision.

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

// Explicit scenario-level mapping tests. These re-assert scenario-to-branch
// mapping so future readers see the three run-page outcomes named directly.
describe("run page error routing scenarios", () => {
  it("scenario 1: 500 with ErrorWithTrace body -> renders <ErrorWithTrace>", () => {
    const fetch_error = {
      message: "The model's output didn't match the expected format.",
      error_type: "JSONSchemaValidationError",
      trace: [
        { role: "system", content: "You are a helpful assistant." },
        { role: "user", content: "hi" },
        { role: "assistant", content: "not valid json" },
      ],
    }
    expect(looks_like_error_with_trace(fetch_error)).toBe(true)
  })

  it("scenario 2: 500 with plain {detail: ...} body -> FormContainer fallback", () => {
    const fetch_error = { detail: "Task configuration was deleted." }
    expect(looks_like_error_with_trace(fetch_error)).toBe(false)
  })

  it("scenario 3: network failure surfaces non-object fetch_error -> FormContainer fallback", () => {
    // openapi-fetch returns the raw text when the body isn't JSON; a thrown
    // fetch error at the transport layer never reaches this branch (it bubbles
    // to the outer catch) but we still guard against it here.
    expect(looks_like_error_with_trace("")).toBe(false)
    expect(looks_like_error_with_trace(undefined)).toBe(false)
  })
})
