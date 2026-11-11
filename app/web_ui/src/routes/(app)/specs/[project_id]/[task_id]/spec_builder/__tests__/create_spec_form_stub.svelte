<script lang="ts">
  import type { KilnError } from "$lib/utils/error_handlers"
  import type { Priority } from "$lib/types"
  import type { FieldConfig } from "../../select_template/spec_templates"

  export let name: string
  export let property_values: Record<string, string | null>
  export let initial_property_values: Record<string, string | null>
  export let priority: Priority = 1
  export let field_configs: FieldConfig[]
  export let error: KilnError | null
  export let submitting: boolean
  export let warn_before_unload: boolean
</script>

<input
  data-testid="spec-name"
  data-name={name}
  data-property-count={Object.keys(property_values).length}
  data-initial-property-count={Object.keys(initial_property_values).length}
  data-priority={priority}
  data-field-count={field_configs.length}
  data-error={String(error)}
  data-submitting={submitting}
  data-warn-before-unload={warn_before_unload}
  bind:value={name}
/>
