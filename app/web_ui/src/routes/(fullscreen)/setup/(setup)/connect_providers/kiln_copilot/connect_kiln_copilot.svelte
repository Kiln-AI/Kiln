<script lang="ts">
  import ConnectKilnCopilotSteps from "$lib/ui/kiln_copilot/connect_kiln_copilot_steps.svelte"

  export let onSuccess: () => void
  export let onCancel: () => void
</script>

<div class="grow h-full max-w-[400px] flex flex-col place-content-center">
  <div class="grow"></div>

  <ConnectKilnCopilotSteps {onSuccess} />

  <button class="link text-center text-sm mt-8" on:click={onCancel}>
    Cancel setting up Kiln Copilot
  </button>

  <div class="grow-[1.5]"></div>
</div>
