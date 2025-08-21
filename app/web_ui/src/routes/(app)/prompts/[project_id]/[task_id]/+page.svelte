<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { current_task, current_task_prompts } from "$lib/stores"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Prompts"
    subtitle={`Prompts for the task "${$current_task?.name}"`}
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/prompts"
    action_buttons={[
      {
        label: "Create Prompt",
        href: `/prompts/${project_id}/${task_id}/create`,
        primary: true,
      },
    ]}
  >
    {#if !$current_task_prompts}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if $current_task?.id != task_id}
      <div class="flex flex-col gap-4 text-error">
        This link is to another task's prompts. Either select that task in the
        sidebar, or click prompts in the sidebar to load the current task's
        prompts.
      </div>
    {:else}
      <div class="font-medium">Prompt Generators</div>
      {#if $current_task_prompts.generators.length > 0}
        <div class="font-light text-gray-500 text-sm">
          Generators build prompts dynamically based on the
          <a href={`/settings/edit_task/${project_id}/${task_id}`} class="link"
            >task's default prompt</a
          >
          and the
          <a href={`/dataset/${project_id}/${task_id}`} class="link"
            >task's dataset</a
          >. For example, the multi-shot prompt appends highly rated dataset
          samples to the prompt.
        </div>
        <div class="overflow-x-auto rounded-lg border mt-4">
          <table class="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {#each $current_task_prompts.generators as generator}
                <tr
                  class="hover:bg-base-200 cursor-pointer"
                  on:click={() =>
                    goto(
                      `/prompts/${project_id}/${task_id}/generator_details/${generator.id}`,
                    )}
                >
                  <td class="font-medium">{generator.name}</td>
                  <td>{generator.short_description}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <div class="font-light text-gray-500 text-sm">
          No prompt generators found for this task.
        </div>
      {/if}

      <div class="font-medium mt-8">Saved Prompts</div>
      {#if $current_task_prompts.prompts.length > 0}
        <div class="font-light text-gray-500 text-sm">
          <a href={`/prompts/${project_id}/${task_id}/create`} class="link">
            Create a new prompt
          </a>
        </div>
        <div class="overflow-x-auto rounded-lg border mt-4">
          <table class="table">
            <thead>
              <tr>
                <th>Name &amp; Description</th>
                <th>Type</th>
                <th>Prompt Preview</th>
              </tr>
            </thead>
            <tbody>
              {#each $current_task_prompts.prompts as prompt}
                <tr
                  class="hover:bg-base-200 cursor-pointer"
                  on:click={() =>
                    goto(
                      `/prompts/${project_id}/${task_id}/saved/${prompt.id}`,
                    )}
                >
                  <td class="font-medium">
                    <div class="font-medium">
                      {prompt.name}
                    </div>
                    <div
                      class="max-w-[220px] font-light text-sm text-gray-500 overflow-hidden {prompt.description
                        ? 'block'
                        : 'hidden'}"
                    >
                      {prompt.description}
                    </div>
                  </td>
                  <td class="min-w-[120px]">
                    {#if prompt.id.startsWith("id::")}
                      Custom
                    {:else if prompt.id.startsWith("fine_tune_prompt::")}
                      Fine Tuning Prompt
                    {:else if prompt.id.startsWith("task_run_config::")}
                      Eval Prompt
                    {:else}
                      Unknown
                    {/if}
                  </td>
                  <td>
                    {prompt.prompt.length > 100
                      ? prompt.prompt.slice(0, 200) + "..."
                      : prompt.prompt}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <div class="font-light text-gray-500 text-sm">
          No saved prompts found for this task.{" "}
          <a href={`/prompts/${project_id}/${task_id}/create`} class="link">
            Create one now
          </a>
          .
        </div>
      {/if}
    {/if}
  </AppPage>
</div>
