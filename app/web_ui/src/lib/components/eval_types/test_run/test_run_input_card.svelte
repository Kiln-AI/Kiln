<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { TaskRunOutput } from "$lib/types"

  export let run: TaskRunOutput
  export let variant: "selected" | "pick" = "selected"
  export let disabled: boolean = false

  const dispatch = createEventDispatcher<{
    change: void
    select: TaskRunOutput
  }>()

  $: input_text = run.input ?? ""
  $: output_text = run.output?.output ?? ""
</script>

{#if variant === "selected"}
  <div
    class="rounded-lg border border-base-300 bg-base-200/50 p-3 flex flex-col gap-2"
    data-testid="selected-run-card"
  >
    <div class="flex items-center justify-between">
      <span class="text-xs font-medium text-base-content"
        >Selected Test Run</span
      >
      <button
        type="button"
        class="btn btn-xs btn-ghost text-primary"
        {disabled}
        on:click={() => dispatch("change")}
      >
        Change
      </button>
    </div>
    <div class="flex flex-col gap-1.5">
      <div class="text-xs">
        <span class="font-medium text-base-content/60">Input</span>
        <p
          class="text-base-content/70 break-words mt-0.5 line-clamp-2"
          title={input_text}
        >
          {input_text}
        </p>
      </div>
      <div class="text-xs">
        <span class="font-medium text-base-content/60">Output</span>
        <p
          class="text-base-content/70 break-words mt-0.5 line-clamp-2"
          title={output_text}
        >
          {output_text}
        </p>
      </div>
    </div>
  </div>
{:else}
  <button
    type="button"
    class="w-full text-left rounded-lg border border-base-300 hover:border-primary/30 hover:bg-base-200/30 p-2.5 flex flex-col gap-1 transition-colors cursor-pointer"
    data-testid="quick-pick-card"
    on:click={() => dispatch("select", run)}
  >
    <div class="text-xs">
      <span class="font-medium text-base-content/40">Input</span>
      <p
        class="text-base-content/70 break-words mt-0.5 line-clamp-2"
        title={input_text}
      >
        {input_text}
      </p>
    </div>
    <div class="text-xs">
      <span class="font-medium text-base-content/40">Output</span>
      <p
        class="text-base-content/70 break-words mt-0.5 line-clamp-2"
        title={output_text}
      >
        {output_text}
      </p>
    </div>
  </button>
{/if}
