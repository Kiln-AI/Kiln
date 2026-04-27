<script lang="ts">
  import { page } from "$app/stores"
  import { get_task_composite_id } from "$lib/stores"
  import { prompts_by_task_composite_id } from "$lib/stores/prompts_store"
  import AppPage from "../../../../../app_page.svelte"
  import Output from "$lib/ui/output.svelte"
  import { formatDate } from "$lib/utils/formatters"
  import EditDialog from "$lib/ui/edit_dialog.svelte"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: prompt_id = $page.params.prompt_id!
  $: agentInfo.set({
    name: "Saved Prompt Detail",
    description: `Saved prompt detail for prompt ID ${prompt_id} in project ID ${project_id}, task ID ${task_id}. Prompt name: ${prompt_model?.name ?? "[loading]"}. Shows prompt content, version history, and options to clone or edit.`,
  })

  $: prompt_model =
    $prompts_by_task_composite_id[
      get_task_composite_id(project_id, task_id)
    ]?.prompts.find((p) => p.id === prompt_id) ?? null

  let prompt_props: Record<string, string | undefined | null> = {}
  $: {
    prompt_props = Object.fromEntries(
      Object.entries({
        ID: prompt_model?.id,
        Name: prompt_model?.name,
        Description: prompt_model?.description || undefined,
        Type: prompt_model?.type ?? "Unknown",
        "Created By": prompt_model?.created_by,
        "Created At": formatDate(prompt_model?.created_at || undefined),
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
        label: "Optimize",
        href: `/optimize/${project_id}/${task_id}`,
      },
      {
        label: "Prompts",
        href: `/prompts/${project_id}/${task_id}`,
      },
    ]}
    action_buttons={[
      ...(prompt_model
        ? [
            {
              label: "Clone",
              href: `/prompts/${project_id}/${task_id}/clone/${encodeURIComponent(prompt_model.id)}`,
            },
          ]
        : []),
      ...(prompt_model?.id.startsWith("id::")
        ? [
            {
              label: "Edit",
              handler: () => {
                edit_dialog?.show()
              },
            },
          ]
        : []),
    ]}
  >
    {#if prompt_model}
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
  warning="Prompt body is locked to preserve consistency of past data. If you want to edit the prompt body, create a new prompt."
  patch_url={`/api/projects/${project_id}/tasks/${task_id}/prompts/${prompt_id}`}
  delete_url={`/api/projects/${project_id}/tasks/${task_id}/prompts/${prompt_id}`}
  fields={[
    {
      label: "Prompt Name",
      api_name: "name",
      value: prompt_model?.name || "",
      input_type: "input",
    },
    {
      label: "Prompt Description",
      api_name: "description",
      optional: true,
      value: prompt_model?.description || "",
      input_type: "textarea",
    },
  ]}
/>
