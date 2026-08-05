<script lang="ts">
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  export let fancy_select_options: OptionGroup[] = []
  export let value: string[] = []
</script>

<div
  data-testid="form-element-options"
  data-option-values={JSON.stringify(
    fancy_select_options.flatMap((group) =>
      group.options.map((option) => option.value),
    ),
  )}
  data-value={JSON.stringify(value)}
></div>
