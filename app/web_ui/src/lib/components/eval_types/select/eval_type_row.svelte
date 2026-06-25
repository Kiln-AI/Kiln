<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type {
    V2EvalType,
    V2EvalTypeMetadata,
  } from "$lib/utils/eval_types/registry"
  import EvalTypeTags from "./eval_type_tags.svelte"
  import EvalTypeIcon from "$lib/components/eval_types/eval_type_icon.svelte"

  export let evalType: V2EvalType
  export let metadata: V2EvalTypeMetadata
  export let recommended: boolean = false

  const dispatch = createEventDispatcher<{ select: void }>()
</script>

<button
  data-testid="eval-type-row"
  class="card card-bordered shadow-md hover:shadow-lg hover:border-primary/50 transition-all duration-200 w-full text-left cursor-pointer {recommended
    ? 'border-base-300 border-2 bg-base-200 p-5'
    : 'border-base-300 p-4'}"
  on:click={() => dispatch("select")}
>
  <div class="flex items-center gap-4">
    <div
      class="flex items-center justify-center rounded-lg flex-none text-primary {recommended
        ? 'w-12 h-12 bg-base-100'
        : 'w-9 h-9 bg-base-200'}"
    >
      <div class={recommended ? "w-6 h-6" : "w-4 h-4"} aria-hidden="true">
        <EvalTypeIcon {evalType} />
      </div>
    </div>

    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2 flex-wrap">
        <span
          class="whitespace-nowrap {recommended
            ? 'font-medium text-base'
            : 'font-medium text-sm'}">{metadata.label}</span
        >
        {#if recommended}
          <span class="badge badge-sm badge-primary">&#9733; Recommended</span>
        {/if}
        <EvalTypeTags tags={metadata.tags} />
      </div>
      <p class="text-gray-500 mt-0.5 {recommended ? 'text-sm' : 'text-xs'}">
        {metadata.description}
      </p>
    </div>

    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="currentColor"
      class="flex-none ml-auto text-gray-500"
      aria-hidden="true"
    >
      <path
        fill-rule="evenodd"
        d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"
      />
    </svg>
  </div>
</button>
