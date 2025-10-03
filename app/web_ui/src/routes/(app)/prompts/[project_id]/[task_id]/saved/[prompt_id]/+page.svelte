<script lang="ts">
  import { page } from "$app/stores"
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

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: prompt_id = $page.params.prompt_id

  $: prompt_model = $current_task_prompts?.prompts.find(
    (prompt) => prompt.id === prompt_id,
  )
  let prompt_props: Record<string, string | undefined | null> = {}
  $: {
    prompt_props = Object.fromEntries(
      Object.entries({
        ID: prompt_model?.id,
        Name: prompt_model?.name,
        Description: prompt_model?.description,
        "Created By": prompt_model?.created_by,
        "Created At": formatDate(prompt_model?.created_at || undefined),
        "Chain of Thought": prompt_model?.chain_of_thought_instructions
          ? "Yes"
          : "No",
        "Source Generator": prompt_model?.generator_id
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
    title="Saved Prompt"
    subtitle={prompt_model?.name}
    sub_subtitle={prompt_model?.description || undefined}
    breadcrumbs={[
      {
        label: "Prompts",
        href: `/prompts/${project_id}/${task_id}`,
      },
    ]}
    action_buttons={prompt_model?.id.startsWith("id::")
      ? [
          {
            label: "Edit",
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
        This link is to another task's prompt. Either select that task in the
        sidebar, or click 'Prompts' in the sidebar to load the current task's
        prompts.
      </div>
    {:else if prompt_model}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-8">
        <div class="grow">
          <div class="text-xl font-bold mb-2">Prompt</div>
          <Output raw_output={prompt_model.prompt} />
          {#if prompt_model.chain_of_thought_instructions}
            <div class="text-xl font-bold mt-10 mb-2">
              Chain of Thought Instructions
            </div>
            <Output raw_output={prompt_model.chain_of_thought_instructions} />
          {/if}
        </div>
        <div class="w-[320px] 2xl:w-96 flex-none flex flex-col gap-4">
          <div class="text-xl font-bold">Details</div>
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
        </div>
      </div>
    {:else}
      <div class="text-error">Prompt not found.</div>
    {/if}
  </AppPage>
</div>

<EditDialog
  bind:this={edit_dialog}
  name="Prompt"
  subtitle="Prompt content can't be edited to ensure consistency with prior runs. If you want to modify the content, create a new prompt instead of editing."
  patch_url={`/api/projects/${$current_project?.id}/tasks/${task_id}/prompts/${prompt_id}`}
  delete_url={`/api/projects/${$current_project?.id}/tasks/${task_id}/prompts/${prompt_id}`}
  fields={[
    {
      label: "Prompt Name",
      description: "The name of the prompt",
      api_name: "name",
      value: prompt_model?.name || "",
      input_type: "input",
    },
    {
      label: "Description",
      description: "The description of the prompt",
      api_name: "description",
      optional: true,
      value: prompt_model?.description || "",
      input_type: "textarea",
    },
  ]}
/>
