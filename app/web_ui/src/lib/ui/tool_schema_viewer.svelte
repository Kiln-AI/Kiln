<script lang="ts">
  import Output from "$lib/ui/output.svelte"

  export let inputSchema: Record<string, unknown> | null | undefined
  export let outputSchema: Record<string, unknown> | null | undefined
  export let inputTitle = "Input"
  export let outputTitle = "Output"

  $: inputSchemaOutput =
    inputSchema && Object.keys(inputSchema).length > 0
      ? JSON.stringify(inputSchema, null, 2)
      : "plaintext"

  $: outputSchemaOutput =
    outputSchema && Object.keys(outputSchema).length > 0
      ? JSON.stringify(outputSchema, null, 2)
      : "plaintext"
</script>

<div class="flex flex-col gap-3">
  <div>
    <div class="text-xs font-medium text-gray-700">{inputTitle}</div>
    <div class="mt-1">
      <Output raw_output={inputSchemaOutput} />
    </div>
  </div>
  <div>
    <div class="text-xs font-medium text-gray-700">{outputTitle}</div>
    <div class="mt-1">
      <Output raw_output={outputSchemaOutput} />
    </div>
  </div>
</div>
