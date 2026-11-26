import { describe, it, expect } from "vitest"
import { option_description_for_display } from "./fancy_select_types"

describe("option_description_for_display", () => {
  it("removes blank lines between paragraphs, keeping single line breaks", () => {
    expect(
      option_description_for_display(
        "Add a person.\n\nThe email is unique, so adding\nsomeone twice is refused.",
      ),
    ).toBe(
      "Add a person.\nThe email is unique, so adding\nsomeone twice is refused.",
    )
  })

  it("treats a line of only spaces or tabs as blank, and collapses runs of them", () => {
    expect(option_description_for_display("One.\n  \n\t\n\nTwo.")).toBe(
      "One.\nTwo.",
    )
  })

  it("drops leading and trailing blank lines", () => {
    expect(option_description_for_display("\n\nOne.\n\n")).toBe("One.")
  })

  it("leaves a description without blank lines as it is", () => {
    expect(option_description_for_display("One person, by id.")).toBe(
      "One person, by id.",
    )
  })
})
