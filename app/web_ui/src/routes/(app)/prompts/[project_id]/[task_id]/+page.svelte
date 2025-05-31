<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { current_task, current_task_prompts } from "$lib/stores"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { _ } from "svelte-i18n"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={$_("prompts.page_title")}
    subtitle={$_("prompts.page_subtitle", {
      values: { task_name: $current_task?.name },
    })}
    sub_subtitle={$_("prompts.page_sub_subtitle")}
    sub_subtitle_link="https://docs.getkiln.ai/docs/prompts"
    action_buttons={[
      {
        label: $_("prompts.create_prompt"),
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
        {$_("prompts.task_link_error")}
      </div>
    {:else}
      <div class="font-medium">{$_("prompts.generators_title")}</div>
      {#if $current_task_prompts.generators.length > 0}
        <div class="font-light text-gray-500 text-sm">
          {@html $_("prompts.generators_description", {
            values: {
              task_link: `<a href="/settings/edit_task/${project_id}/${task_id}" class="link">${$_("prompts.task_default_prompt_link")}</a>`,
              dataset_link: `<a href="/dataset/${project_id}/${task_id}" class="link">${$_("prompts.task_dataset_link")}</a>`,
            },
          })}
        </div>
        <div class="overflow-x-auto rounded-lg border mt-4">
          <table class="table">
            <thead>
              <tr>
                <th>{$_("prompts.table_headers.name")}</th>
                <th>{$_("prompts.table_headers.description")}</th>
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
          {$_("prompts.no_generators_found")}
        </div>
      {/if}

      <div class="font-medium mt-8">{$_("prompts.saved_prompts_title")}</div>
      {#if $current_task_prompts.prompts.length > 0}
        <div class="font-light text-gray-500 text-sm">
          <a href={`/prompts/${project_id}/${task_id}/create`} class="link">
            {$_("prompts.create_new_prompt_link")}
          </a>
        </div>
        <div class="overflow-x-auto rounded-lg border mt-4">
          <table class="table">
            <thead>
              <tr>
                <th>{$_("prompts.table_headers.name_and_description")}</th>
                <th>{$_("prompts.table_headers.type")}</th>
                <th>{$_("prompts.table_headers.prompt_preview")}</th>
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
                      {$_("prompts.prompt_types.custom")}
                    {:else if prompt.id.startsWith("fine_tune_prompt::")}
                      {$_("prompts.prompt_types.fine_tune_prompt")}
                    {:else if prompt.id.startsWith("task_run_config::")}
                      {$_("prompts.prompt_types.eval_prompt")}
                    {:else}
                      {$_("prompts.prompt_types.unknown")}
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
          {@html $_("prompts.no_saved_prompts_found", {
            values: {
              create_link: `<a href="/prompts/${project_id}/${task_id}/create" class="link">${$_("prompts.create_one_now")}</a>`,
            },
          })}
        </div>
      {/if}
    {/if}
  </AppPage>
</div>
