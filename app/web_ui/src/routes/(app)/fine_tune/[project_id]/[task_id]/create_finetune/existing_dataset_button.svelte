<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { DatasetSplit } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"

  const dispatch = createEventDispatcher<{ select: DatasetSplit }>()

  export let dataset: DatasetSplit
  export let finetuneNames: string[] = []
  export let disabled = false

  function handleClick() {
    if (disabled) {
      return
    }
    dispatch("select", dataset)
  }

  $: datasetSizeSummary = Object.keys(dataset.split_contents)
    .map((split_type) => {
      return `${dataset.split_contents[split_type].length} in '${split_type}'`
    })
    .join(", ")
</script>

<button
  class="card card-bordered border-base-300 bg-base-200 shadow-md w-full px-4 py-3 indicator grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 overflow-hidden text-left disabled:opacity-50 disabled:cursor-not-allowed"
  on:click={handleClick}
  {disabled}
>
  <div class="text-xs text-gray-500">Dataset Name</div>
  <div class="text-medium">{dataset.name}</div>
  <div class="text-xs text-gray-500">Created</div>
  <div>{formatDate(dataset.created_at)}</div>

  <div class="text-xs text-gray-500">Dataset Size</div>
  <div>{datasetSizeSummary}</div>
  <div class="text-xs text-gray-500">Tunes Using Dataset</div>
  <div>{finetuneNames.join(", ")}</div>
</button>
