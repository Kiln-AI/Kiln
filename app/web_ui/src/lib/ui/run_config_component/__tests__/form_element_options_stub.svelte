<script lang="ts">
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  export let fancy_select_options: OptionGroup[] = []
  export let value: string[] = []
</script>

<<<<<<< HEAD
<div
  data-testid="form-element-options"
=======
<!-- FancySelect renders its empty state when the OPTION GROUP list is empty, so the
     group count is exposed separately from the flattened option values: a picker can
     hold groups that contribute no options (the "Create New" kiln-task affordance). -->
<div
  data-testid="form-element-options"
  data-option-group-count={fancy_select_options.length}
>>>>>>> 721c4941b
  data-option-values={JSON.stringify(
    fancy_select_options.flatMap((group) =>
      group.options.map((option) => option.value),
    ),
  )}
<<<<<<< HEAD
  data-options={JSON.stringify(
    fancy_select_options.flatMap((group) => group.options),
  )}
=======
>>>>>>> 721c4941b
  data-value={JSON.stringify(value)}
></div>
