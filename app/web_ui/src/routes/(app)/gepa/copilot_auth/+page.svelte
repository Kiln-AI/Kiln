<script lang="ts">
  import { goto } from "$app/navigation"
  import { ui_state } from "$lib/stores"
  import ConnectKilnCopilotSteps from "$lib/ui/kiln_copilot/connect_kiln_copilot_steps.svelte"
  import AppPage from "../../app_page.svelte"

  $: project_id = $ui_state.current_project_id
  $: task_id = $ui_state.current_task_id

  let connect_success = false

  function proceed_to_create_gepa() {
    goto(`/gepa/${project_id}/${task_id}/create_gepa`)
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Create Optimized Prompt"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/prompts"
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${task_id}`,
      },
      {
        label: "Prompts",
        href: `/prompts/${project_id}/${task_id}`,
      },
      {
        label: "Optimizer Jobs",
        href: `/gepa/${project_id}/${task_id}`,
      },
    ]}
  >
    <div class="flex flex-col max-w-[400px]">
      <ConnectKilnCopilotSteps
        onSuccess={() => (connect_success = true)}
        showCheckmark={connect_success}
      />
      {#if connect_success}
        <button
          class="btn btn-primary mt-4 w-full"
          on:click={proceed_to_create_gepa}
        >
          Next
        </button>
      {:else}
        <button
          class="link text-center text-sm mt-8"
          on:click={() =>
            goto(`/gepa/${project_id}/${task_id}/create_gepa`, {
              replaceState: true,
            })}
        >
          Cancel setting up Kiln Copilot
        </button>
      {/if}
    </div>
  </AppPage>
</div>
