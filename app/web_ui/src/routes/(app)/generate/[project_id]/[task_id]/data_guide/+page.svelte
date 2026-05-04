<script lang="ts">
  // Saved-guide view: shown when the user already has a saved data guide and
  // revisits to read it. The active refine/preview loop lives at
  // /data_guide/refine; this page hands off to it via a writable store when
  // the user clicks "Test Data Guide" or submits the edit dialog.
  import AppPage from "../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, onDestroy } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import GuideRefineView from "../data_guide_setup/guide_refine_view.svelte"
  import DataGenDescription from "../data_gen_description.svelte"
  import { SynthDataGuidanceDataModel } from "../synth_data_guidance_datamodel"
  import type {
    KilnAgentRunConfigProperties,
    Task,
    DataGuide,
  } from "$lib/types"
  import { agentInfo } from "$lib/agent"
  import { current_task } from "$lib/stores"
  import DeleteDialog from "$lib/ui/delete_dialog.svelte"
  import { isMacOS } from "$lib/utils/platform"
  import { pending_data_guide_refine_handoff } from "./refine_handoff_store"

  type ViewState = "loading" | "saved"

  let current_state: ViewState = "loading"
  let error: KilnError | null = null

  let guide: string = ""
  let saved_data_guide: DataGuide | null = null
  let task: Task | null = null
  // Bound so the AppPage's "Edit" action button can drive the dialog inside
  // GuideRefineView without having to lift the dialog state up here.
  let refine_view: GuideRefineView | null = null

  let guidance_data: SynthDataGuidanceDataModel =
    new SynthDataGuidanceDataModel()
  onDestroy(() => {
    guidance_data.destroy()
  })

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: agentInfo.set({
    name: "Data Guide",
    description: `View and refine the saved task data guide for project ${project_id}, task ${task_id}.`,
  })

  onMount(async () => {
    try {
      const { data } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        { params: { path: { project_id, task_id } } },
      )
      if (data) {
        guide = data.guide
        saved_data_guide = data
      }
    } catch {
      // No existing guide
    }

    // No saved guide → send them to the setup flow.
    if (!guide.trim()) {
      goto(`/generate/${project_id}/${task_id}/data_guide_setup`)
      return
    }

    if ($current_task?.id === task_id) {
      task = $current_task
    } else {
      try {
        const { data: task_data } = await client.GET(
          "/api/projects/{project_id}/tasks/{task_id}",
          { params: { path: { project_id, task_id } } },
        )
        if (task_data) {
          task = task_data
        }
      } catch {
        // Non-critical
      }
    }

    current_state = "saved"
  })

  function handle_generate_preview(
    event: CustomEvent<{
      guide: string
      input_run_config: KilnAgentRunConfigProperties
      output_run_config: KilnAgentRunConfigProperties
    }>,
  ) {
    pending_data_guide_refine_handoff.set({
      guide: event.detail.guide,
      input_run_config: event.detail.input_run_config,
      output_run_config: event.detail.output_run_config,
    })
    goto(`/generate/${project_id}/${task_id}/data_guide/refine`)
  }

  async function handle_save_with_guide(event: CustomEvent<{ guide: string }>) {
    error = null

    try {
      const { data: saved, error: api_error } = await client.PUT(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        {
          params: { path: { project_id, task_id } },
          body: { guide: event.detail.guide },
        },
      )

      if (api_error) throw api_error

      if (saved) {
        saved_data_guide = saved
        guide = saved.guide
      }
    } catch (e) {
      error = createKilnError(e)
    }
  }

  let delete_dialog: DeleteDialog | null = null
  $: delete_url = `/api/projects/${project_id}/tasks/${task_id}/data_gen_guide`
  function after_delete() {
    goto(`/generate/${project_id}/${task_id}/synth`)
  }
</script>

<!-- TODO: Update read the docs link to point to new data guide docs -->
<div class="max-w-[1400px]">
  <AppPage
    title="Data Guide"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/synthetic-data-generation"
    breadcrumbs={[
      {
        label: "Synthetic Data Generation",
        href: `/generate/${project_id}/${task_id}/synth`,
        // This page is a sub-flow of /synth — replace rather than push so
        // back from /synth returns to wherever the user originally came
        // from (cards page, spec page, etc.) instead of bouncing here.
        replace_state: true,
      },
    ]}
    action_buttons={current_state === "saved"
      ? [
          {
            icon: "/images/delete.svg",
            handler: () => delete_dialog?.show(),
            shortcut: isMacOS() ? "Backspace" : "Delete",
          },
          {
            label: "Edit",
            handler: () => refine_view?.open_edit_dialog(),
          },
        ]
      : []}
  >
    <DataGenDescription bind:guidance_data />

    {#if current_state === "loading"}
      <div class="flex flex-col items-center justify-center py-24 gap-4">
        <span class="loading loading-spinner loading-lg text-primary" />
      </div>
    {:else if current_state === "saved"}
      <GuideRefineView
        bind:this={refine_view}
        {project_id}
        {guide}
        {task}
        data_guide={saved_data_guide}
        bind:page_error={error}
        on:generate_preview={handle_generate_preview}
        on:save={handle_save_with_guide}
      />
    {/if}
  </AppPage>
</div>

<DeleteDialog
  name="Data Guide"
  bind:this={delete_dialog}
  {delete_url}
  {after_delete}
/>
