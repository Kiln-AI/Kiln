<script lang="ts">
  import Trace from "$lib/ui/trace/trace.svelte"
  import ErrorDetailsBlock from "$lib/ui/error_details_block.svelte"
  import type { ErrorWithTrace, Trace as TraceType } from "$lib/types"

  export let error: ErrorWithTrace
  export let error_title: string = "Error"
  export let troubleshooting_steps: string[] = []

  // The API response and UI component use slightly different TypeScript types
  // for chat messages (same structure, different type names). Cast once here
  // to satisfy the Trace component's prop typing.
  $: trace_for_viewer = (error.trace ?? []) as TraceType
</script>

{#if error.trace && error.trace.length > 0}
  <Trace trace={trace_for_viewer} />
{/if}

<ErrorDetailsBlock
  title={error_title}
  error_messages={[error.message]}
  {troubleshooting_steps}
/>
