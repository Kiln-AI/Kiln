<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from "svelte"
  import RunInputFormElement from "./run_input_form_element.svelte"
  import { type SchemaModelProperty } from "$lib/utils/json_schema_editor/json_schema_templates"

  export let property: SchemaModelProperty
  export let onInputChange: (() => void) | null = null
  export let level: number = 0
  export let path: string = ""
  export let hideHeaderAndIndent: boolean = false
  export let parentOptional: boolean = false

  const dispatch = createEventDispatcher()
  let inst: RunInputFormElement | null = null

  onMount(() => dispatch("ref", { inst }))
  onDestroy(() => dispatch("ref", { inst: null }))
</script>

<RunInputFormElement
  {property}
  {onInputChange}
  {level}
  {path}
  {hideHeaderAndIndent}
  {parentOptional}
  bind:this={inst}
/>
