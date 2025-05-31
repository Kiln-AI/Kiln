<script lang="ts">
  import { page } from "$app/stores"
  import { _ } from "svelte-i18n"
  import {
    current_project,
    current_task,
    current_task_prompts,
    prompt_name_from_id,
  } from "$lib/stores"
  import AppPage from "../../../../../app_page.svelte"
  import Output from "../../../../../run/output.svelte"
  import { formatDate } from "$lib/utils/formatters"
  import EditDialog from "$lib/ui/edit_dialog.svelte"

  $: task_id = $page.params.task_id
  $: prompt_id = $page.params.prompt_id

  $: prompt_model = $current_task_prompts?.prompts.find(
    (prompt) => prompt.id === prompt_id,
  )
  let prompt_props: Record<string, string | undefined | null> = {}
  $: {
    prompt_props = Object.fromEntries(
      Object.entries({
        [$_("prompts.saved_prompt.details_fields.id")]: prompt_model?.id,
        [$_("prompts.saved_prompt.details_fields.name")]: prompt_model?.name,
        [$_("prompts.saved_prompt.details_fields.description")]:
          prompt_model?.description,
        [$_("prompts.saved_prompt.details_fields.created_by")]:
          prompt_model?.created_by,
        [$_("prompts.saved_prompt.details_fields.created_at")]: formatDate(
          prompt_model?.created_at || undefined,
        ),
        [$_("prompts.saved_prompt.details_fields.chain_of_thought")]:
          prompt_model?.chain_of_thought_instructions
            ? $_("common.yes")
            : $_("common.no"),
        [$_("prompts.saved_prompt.details_fields.source_generator")]:
          prompt_model?.generator_id
            ? prompt_name_from_id(
                prompt_model?.generator_id,
                $current_task_prompts,
              )
            : undefined,
      }).filter(([_, value]) => value !== undefined && value !== null),
    )
  }

  let edit_dialog: EditDialog | null = null
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={$_("prompts.saved_prompt.title")}
    subtitle={prompt_model?.name}
    sub_subtitle={prompt_model?.description || undefined}
    action_buttons={prompt_model?.id.startsWith("id::")
      ? [
          {
            label: $_("common.edit"),
            handler: () => {
              edit_dialog?.show()
            },
          },
        ]
      : []}
  >
    {#if !$current_task_prompts}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if $current_task?.id != task_id}
      <div class="text-error">
        {$_("prompts.saved_prompt.task_link_error")}
      </div>
    {:else if prompt_model}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-8">
        <div class="grow">
          <div class="text-xl font-bold mb-2">{$_("prompts.prompt_label")}</div>
          <Output raw_output={prompt_model.prompt} />
          {#if prompt_model.chain_of_thought_instructions}
            <div class="text-xl font-bold mt-10 mb-2">
              {$_("prompts.chain_of_thought_instructions")}
            </div>
            <Output raw_output={prompt_model.chain_of_thought_instructions} />
          {/if}
        </div>
        <div class="w-[320px] 2xl:w-96 flex-none flex flex-col gap-4">
          <div class="text-xl font-bold">
            {$_("prompts.saved_prompt.details")}
          </div>
          <div
            class="grid grid-cols-[auto,1fr] gap-y-2 gap-x-4 text-sm 2xl:text-base"
          >
            {#each Object.entries(prompt_props) as [key, value]}
              <div class="flex items-center">{key}</div>
              <div
                class="flex items-center text-gray-500 break-words overflow-hidden"
              >
                {value}
              </div>
            {/each}
          </div>
          <p class="mt-4 text-sm text-gray-500">
            {$_("prompts.saved_prompt.edit_note")}
          </p>
        </div>
      </div>
    {:else}
      <div class="text-error">
        {$_("prompts.saved_prompt.prompt_not_found")}
      </div>
    {/if}
  </AppPage>
</div>

<EditDialog
  bind:this={edit_dialog}
  name={$_("prompts.saved_prompt.title")}
  patch_url={`/api/projects/${$current_project?.id}/tasks/${task_id}/prompts/${prompt_id}`}
  delete_url={`/api/projects/${$current_project?.id}/tasks/${task_id}/prompts/${prompt_id}`}
  fields={[
    {
      label: $_("prompts.prompt_name"),
      description: $_("prompts.prompt_name_description"),
      api_name: "name",
      value: prompt_model?.name || "",
      input_type: "input",
    },
    {
      label: $_("prompts.prompt_description"),
      description: $_("prompts.prompt_description_description"),
      api_name: "description",
      optional: true,
      value: prompt_model?.description || "",
      input_type: "textarea",
    },
  ]}
/>
