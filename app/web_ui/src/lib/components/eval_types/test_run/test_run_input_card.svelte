<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { TaskRunOutput } from "$lib/types"
  import ClampedText from "$lib/ui/clamped_text.svelte"
  import { formatExpandedContent } from "$lib/utils/format_expanded_content"

  export let run: TaskRunOutput
  export let variant: "selected" | "pick" = "selected"
  export let disabled: boolean = false

  const dispatch = createEventDispatcher<{
    change: void
    select: TaskRunOutput
    see_all: { title: string; content: string }
  }>()

  $: input_text = run.input ?? ""
  $: output_text = run.output?.output ?? ""
  $: input_content = formatExpandedContent(input_text)
  $: output_content = formatExpandedContent(output_text)
</script>

{#if variant === "selected"}
  <div
    class="rounded-lg border border-base-300 bg-base-200/50 p-3 flex flex-col gap-2"
    data-testid="selected-run-card"
  >
    <div class="flex items-center justify-between">
      <span class="font-medium text-base">Selected Test Run</span>
      <button
        class="link underline text-xs text-gray-500"
        {disabled}
        on:click={() => dispatch("change")}
      >
        Change
      </button>
    </div>
    <div class="flex flex-col gap-1.5">
      <div class="text-xs">
        <span class="font-medium text-gray-500">Input</span>
        <ClampedText
          content={input_content.isJson ? "" : input_content.value}
          html_content={input_content.isJson ? input_content.value : null}
          text_class="whitespace-pre-wrap break-words text-xs text-gray-500 mt-0.5"
          on:see_all={() =>
            dispatch("see_all", { title: "Input", content: input_text })}
        />
      </div>
      <div class="text-xs">
        <span class="font-medium text-gray-500">Output</span>
        <ClampedText
          content={output_content.isJson ? "" : output_content.value}
          html_content={output_content.isJson ? output_content.value : null}
          text_class="whitespace-pre-wrap break-words text-xs text-gray-500 mt-0.5"
          on:see_all={() =>
            dispatch("see_all", { title: "Output", content: output_text })}
        />
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
      <span class="font-medium text-gray-500">Input</span>
      <p
        class="text-gray-500 break-words mt-0.5 line-clamp-2"
        title={input_text}
      >
        {input_text}
      </p>
    </div>
    <div class="text-xs">
      <span class="font-medium text-gray-500">Output</span>
      <p
        class="text-gray-500 break-words mt-0.5 line-clamp-2"
        title={output_text}
      >
        {output_text}
      </p>
    </div>
  </button>
{/if}
