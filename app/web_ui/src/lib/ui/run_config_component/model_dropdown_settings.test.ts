import { describe, it, expect } from "vitest"
import { show_suggested_advisory } from "./model_dropdown_settings"

describe("show_suggested_advisory", () => {
  it("always renders when the caller is not quiet", () => {
    for (const model_selected of [true, false]) {
      for (const model_is_suggested of [true, false]) {
        for (const suggestion_known of [true, false]) {
          expect(
            show_suggested_advisory(
              model_selected,
              model_is_suggested,
              false,
              suggestion_known,
            ),
          ).toBe(true)
        }
      }
    }
  })

  it("hides only the chosen-and-suggested state when quiet", () => {
    // The one state that tells the user nothing they can act on.
    expect(show_suggested_advisory(true, true, true, true)).toBe(false)
    // A chosen model that is not suggested is a warning: it survives.
    expect(show_suggested_advisory(true, false, true, true)).toBe(true)
    // No model chosen yet: the prompt to choose one survives.
    expect(show_suggested_advisory(false, false, true, true)).toBe(true)
    expect(show_suggested_advisory(false, true, true, true)).toBe(true)
  })

  it("waits for the model list before judging a chosen model when quiet", () => {
    // Mid-load every model reads as not-suggested, so rendering here would show
    // a warning that a suggested model then removes — a visible jump.
    expect(show_suggested_advisory(true, false, true, false)).toBe(false)
    expect(show_suggested_advisory(true, true, true, false)).toBe(false)
    // With no model chosen there is nothing to look up, so the prompt to choose
    // one renders straight away.
    expect(show_suggested_advisory(false, false, true, false)).toBe(true)
  })
})
