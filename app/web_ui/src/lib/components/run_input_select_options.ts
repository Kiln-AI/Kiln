import type { OptionGroup } from "$lib/ui/fancy_select_types"

export const NOT_SET_LABEL = "Not Set"

/**
 * The dropdown options for an enum field. An optional enum leads with "Not Set",
 * its default; a required one lists it last so a value has to be picked.
 */
export function enum_select_options(
  values: unknown[],
  optional: boolean,
): OptionGroup[] {
  const not_set = { label: NOT_SET_LABEL, value: undefined }
  const enum_options = values.map((value) => ({
    label: (value ?? "null").toString(),
    value,
  }))
  return [
    {
      options: optional
        ? [not_set, ...enum_options]
        : [...enum_options, not_set],
    },
  ]
}
