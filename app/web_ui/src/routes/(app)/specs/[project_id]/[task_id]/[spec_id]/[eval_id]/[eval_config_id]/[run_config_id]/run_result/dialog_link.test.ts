import { describe, it, expect } from "vitest"
import {
  dialog_link_from_hash,
  dialog_link_hash,
  type LinkedDialog,
} from "./dialog_link"

describe("dialog link hash", () => {
  it("builds a hash naming the dialog and the eval run", () => {
    expect(
      dialog_link_hash({ dialog: "trace", eval_run_id: "212038905177" }),
    ).toBe("#trace-212038905177")
    expect(
      dialog_link_hash({ dialog: "reasoning", eval_run_id: "212038905177" }),
    ).toBe("#reasoning-212038905177")
  })

  it("reads back the link it was built from", () => {
    const dialogs: LinkedDialog[] = ["trace", "reasoning"]
    for (const dialog of dialogs) {
      for (const eval_run_id of ["212038905177", "id with spaces", "a/b#c%d"]) {
        const link = { dialog, eval_run_id }
        expect(dialog_link_from_hash(dialog_link_hash(link))).toEqual(link)
      }
    }
  })

  it("ignores hashes that are not dialog links", () => {
    for (const hash of [
      "",
      "#",
      "#trace",
      "#trace-",
      "#reasoning-",
      "#other-123",
      "trace-1",
      "reasoning-1",
    ]) {
      expect(dialog_link_from_hash(hash)).toBeNull()
    }
  })

  it("ignores a link whose id is not valid percent-encoding", () => {
    expect(dialog_link_from_hash("#trace-%E0%A4%A")).toBeNull()
    expect(dialog_link_from_hash("#reasoning-%E0%A4%A")).toBeNull()
  })
})
