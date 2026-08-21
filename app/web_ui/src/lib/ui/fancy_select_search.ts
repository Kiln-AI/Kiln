import type { OptionGroup } from "./fancy_select_types"

// Which options survive a dropdown search. Multi-word and order-independent: every
// word typed has to appear somewhere in an option's searchable text.
//
// That text is the label, the description and the badge. Badges carry identity the
// label does not -- a tool's OpenAI function name, "Recommended", "Requires API
// Key" -- and anything the user can read on an option should be something they can
// find it by.
//
// Groups left with nothing matching are dropped, so a search never leaves a bare
// header behind.
export function filter_option_groups(
  options: OptionGroup[],
  search_text: string,
): OptionGroup[] {
  if (!search_text.trim()) {
    return options
  }

  const search_words = search_text.toLowerCase().trim().split(/\s+/)

  return options
    .map((group) => ({
      ...group,
      options: group.options.filter((option) => {
        const searchable_text = [option.label, option.description, option.badge]
          .filter((text) => !!text)
          .join(" ")
          .toLowerCase()
        return search_words.every((word) => searchable_text.includes(word))
      }),
    }))
    .filter((group) => group.options.length > 0)
}
