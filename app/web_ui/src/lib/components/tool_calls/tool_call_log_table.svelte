<script lang="ts">
  import type { components } from "$lib/api_schema"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  type ToolCallLogEntry = components["schemas"]["ToolCallLogEntryResponse"]

  // Calls user-authored sandboxed code made over the tool bridge. Shared by the
  // code-tool and code-eval test panes, which both run that code and both need the
  // same thing from it: what was called, with what, what came back, and how long.
  export let entries: ToolCallLogEntry[] = []
  export let title: string = "Internal Tool Calls"
  export let tooltip_text: string | undefined = undefined

  function pretty(value: string): string {
    try {
      return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
      return value
    }
  }
</script>

{#if entries.length > 0}
  <div class="flex flex-col gap-1" data-testid="tool-call-log">
    <div class="flex items-center justify-between">
      <span class="text-sm font-medium">{title}</span>
      {#if tooltip_text}
        <InfoTooltip {tooltip_text} />
      {/if}
    </div>
    <div class="overflow-x-auto rounded-lg border">
      <table class="table table-xs">
        <thead>
          <tr>
            <th>Function</th>
            <th>Arguments</th>
            <th>Result</th>
            <th>Duration</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {#each entries as entry}
            <tr>
              <td class="font-mono text-xs">{entry.tool_name}</td>
              <td class="text-xs max-w-[120px]">
                <details>
                  <summary class="cursor-pointer truncate"
                    >{JSON.stringify(entry.arguments)}</summary
                  >
                  <pre
                    class="whitespace-pre-wrap font-mono mt-1">{JSON.stringify(
                      entry.arguments,
                      null,
                      2,
                    )}</pre>
                </details>
              </td>
              <!-- For a failed call the recorder puts the error message in
                   output_preview, so this column is the only place an author can
                   see why a call failed. -->
              <td class="text-xs max-w-[120px]">
                {#if entry.output_preview}
                  <details>
                    <summary
                      class="cursor-pointer truncate"
                      class:text-error={entry.is_error}
                      >{entry.output_preview}</summary
                    >
                    <pre class="whitespace-pre-wrap font-mono mt-1">{pretty(
                        entry.output_preview,
                      )}</pre>
                  </details>
                {:else}
                  <span class="text-gray-500">—</span>
                {/if}
              </td>
              <td class="text-xs">{entry.duration_ms}ms</td>
              <td class="text-xs">
                {#if entry.is_error}
                  <span class="badge badge-error badge-xs">Error</span>
                {:else}
                  <span class="badge badge-success badge-xs">OK</span>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
{/if}
