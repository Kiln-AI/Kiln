import { describe, it, expect } from "vitest"
import type { OptionGroup } from "./fancy_select_types"
import { filter_option_groups } from "./fancy_select_search"

const option_groups: OptionGroup[] = [
  {
    label: "Models",
    options: [
      { value: "gpt_4o", label: "GPT 4o", badge: "Recommended" },
      {
        value: "llama_3",
        label: "Llama 3",
        description: "Runs on your own hardware",
      },
    ],
  },
  {
    label: "Tools",
    options: [{ value: "counter", label: "Counter", badge: "word_count" }],
  },
]

const matches = (search_text: string): string[] =>
  filter_option_groups(option_groups, search_text).flatMap((group) =>
    group.options.map((option) => String(option.value)),
  )

describe("filter_option_groups", () => {
  it("returns every group untouched when nothing is typed", () => {
    expect(filter_option_groups(option_groups, "")).toEqual(option_groups)
    expect(filter_option_groups(option_groups, "   ")).toEqual(option_groups)
  })

  it("matches on the option label", () => {
    expect(matches("llama")).toEqual(["llama_3"])
  })

  it("matches on the option description", () => {
    expect(matches("hardware")).toEqual(["llama_3"])
  })

  it("matches on the badge, which carries identity the label does not", () => {
    // A tool option badges the OpenAI function name a trace records -- the value
    // being picked -- so it has to be findable. So do "Recommended" and friends.
    expect(matches("word_count")).toEqual(["counter"])
    expect(matches("recommended")).toEqual(["gpt_4o"])
  })

  it("matches badge text case-insensitively", () => {
    expect(matches("RECOMMENDED")).toEqual(["gpt_4o"])
  })

  it("requires every word, in any order, across label, description and badge", () => {
    expect(matches("recommended gpt")).toEqual(["gpt_4o"])
    // A badge cannot rescue an option whose other words do not match.
    expect(matches("llama recommended")).toEqual([])
  })

  it("does not let one option's text match against a neighbour's", () => {
    expect(matches("counter recommended")).toEqual([])
  })

  it("drops a group left with no matching options", () => {
    expect(
      filter_option_groups(option_groups, "recommended").map(
        (group) => group.label,
      ),
    ).toEqual(["Models"])
  })

  it("keeps a group's own fields when filtering its options", () => {
    const with_action: OptionGroup[] = [
      {
        label: "Tools",
        options: [{ value: "counter", label: "Counter", badge: "word_count" }],
        action_label: "Create New",
        action_handler: () => {},
      },
    ]
    const [group] = filter_option_groups(with_action, "counter")
    expect(group.action_label).toBe("Create New")
    expect(group.action_handler).toBe(with_action[0].action_handler)
  })
})
