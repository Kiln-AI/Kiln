import { describe, it, expect } from "vitest"
import { eval_run_id_from_trace_hash, trace_link_hash } from "./trace_link"

describe("trace link hash", () => {
  it("builds a hash naming the eval run", () => {
    expect(trace_link_hash("212038905177")).toBe("#trace-212038905177")
  })

  it("reads back the eval run id it was built from", () => {
    for (const id of ["212038905177", "id with spaces", "a/b#c%d"]) {
      expect(eval_run_id_from_trace_hash(trace_link_hash(id))).toBe(id)
    }
  })

  it("ignores hashes that are not trace links", () => {
    for (const hash of [
      "",
      "#",
      "#trace",
      "#trace-",
      "#other-123",
      "trace-1",
    ]) {
      expect(eval_run_id_from_trace_hash(hash)).toBeNull()
    }
  })

  it("ignores a trace hash whose id is not valid percent-encoding", () => {
    expect(eval_run_id_from_trace_hash("#trace-%E0%A4%A")).toBeNull()
  })
})
