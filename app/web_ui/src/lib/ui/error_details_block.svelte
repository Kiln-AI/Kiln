<script lang="ts">
  import Output from "./output.svelte"
  import MarkdownBlock from "./markdown_block.svelte"
  import { view_logs } from "$lib/utils/logs"

  export let title: string
  export let error_messages: string[]
  export let troubleshooting_steps: string[] = []
  export let markdown: boolean = false
  export let trusted: boolean = false
  export let show_logs: boolean = true
</script>

<div
  class="mb-6 flex flex-col gap-4 max-w-[600px] mx-auto border p-4 rounded-md"
>
  <span class="font-bold text-error">{title}</span>

  {#if troubleshooting_steps.length > 0}
    <div class="flex flex-col gap-2">
      <span class="font-medium">Troubleshooting Steps</span>
      <ol class="text-sm list-decimal list-outside pl-6 flex flex-col gap-2">
        {#each troubleshooting_steps as step}
          <li>
            {#if markdown && trusted}
              <MarkdownBlock markdown_text={step} />
            {:else}
              {step}
            {/if}
          </li>
        {/each}
      </ol>
    </div>
  {/if}

  {#if show_logs}
    <div class="flex flex-col gap-2">
      <span class="font-medium">Error Details</span>
      <Output
        raw_output={error_messages.join("\n\n")}
        hide_toggle={false}
        max_height="120px"
      />
    </div>
    <div>
      <button type="button" class="link" on:click={view_logs}>
        View Logs
      </button>
    </div>
  {/if}
</div>
