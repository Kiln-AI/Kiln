import { describe, expect, it } from "vitest"
import { toolStatusVariant } from "./tool_status"

describe("toolStatusVariant", () => {
  it.each([
    // output, isGet, isActiveMessage, expected
    [undefined, true, true, "fetching"],
    [undefined, false, true, "saving"],
    ["result", true, true, "fetched"],
    ["result", false, true, "saved"],
    [undefined, true, false, "fetched"],
    [{ error: "boom" }, true, true, "fetch_failed"],
    [{ error: "boom" }, false, false, "save_failed"],
  ] as const)(
    "output=%j isGet=%s active=%s -> %s",
    (output, isGet, isActiveMessage, expected) => {
      expect(toolStatusVariant(output, isGet, isActiveMessage)).toBe(expected)
    },
  )
})
