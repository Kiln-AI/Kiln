<!--
  A small wrapper that conditionally renders the "Open TaskRun" link with
  its tooltip. Extracted into its own component because inlining
  {#if run_link} inside the deeply-nested meta-row blocks tripped a Svelte
  4 update bug (`Cannot read properties of null (reading 'p')`) when the
  link became available asynchronously after run_chain resolved. Component
  prop updates take a different patch path that does not crash.
-->
<script lang="ts">
  import ArrowRightUpIcon from "../icons/arrow_right_up_icon.svelte"
  export let run_link: string | null
</script>

{#if run_link}
  <div class="tooltip tooltip-top" data-tip="Open TaskRun">
    <a
      href={run_link}
      class="btn btn-xs btn-square btn-ghost text-gray-500 hover:text-gray-900"
      aria-label="Open TaskRun for this turn"
      data-testid="chat-msg-run-link"
    >
      <span class="w-4 h-4 block"><ArrowRightUpIcon /></span>
    </a>
  </div>
{/if}
