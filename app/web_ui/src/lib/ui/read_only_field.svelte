<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"

  export let id: string
  export let label: string
  export let value: string | number
  export let info_description: string | undefined = undefined
</script>

<FormElement {id} {label} inputType="header_only" {info_description} value="" />
<div class="relative">
  <div
    class="select select-bordered w-full flex items-center bg-base-200/50 text-base-content/70"
    style="background-image: none;"
  >
    <span class="truncate">{value}</span>
  </div>
</div>
