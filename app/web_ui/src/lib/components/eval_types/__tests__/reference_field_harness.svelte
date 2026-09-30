<svelte:options accessors />

<script lang="ts">
  import ReferenceFieldSelect from "../form_parts/reference_field_select.svelte"

  export let value: string | null = null
  export let candidate_keys: string[] = []
</script>

<ReferenceFieldSelect id_prefix="t" {candidate_keys} bind:value />
