<script lang="ts">
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  export let inputType: string = "input"
  export let label: string = ""
  export let error_message: string | null = null
  export let fancy_select_options: OptionGroup[] = []
  export let value: unknown = null
  export let empty_state_message: string | null = null
  export let empty_state_subtitle: string | null = null
  export let empty_state_link: string | null = null
</script>

<!-- Exposes the props a FormElement was given, for tests that check what a
     component asks FormElement to render. -->
<div
  data-testid="form-element-props"
  data-input-type={inputType}
  data-label={label}
  data-error-message={error_message}
  data-option-values={JSON.stringify(
    fancy_select_options.flatMap((group) =>
      group.options.map((option) => option.value),
    ),
  )}
  data-option-descriptions={JSON.stringify(
    fancy_select_options.flatMap((group) =>
      group.options.map((option) => option.description),
    ),
  )}
  data-value={JSON.stringify(value)}
  data-empty-state-message={empty_state_message}
  data-empty-state-subtitle={empty_state_subtitle}
  data-empty-state-link={empty_state_link}
></div>
