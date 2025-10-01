<script lang="ts">
  import type { TaskRun, Task } from "$lib/types"
  import Dialog from "../dialog.svelte"
  import InfoTooltip from "../info_tooltip.svelte"
  import TraceComponent from "./trace.svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"

  export let project_id: string | undefined = undefined

  let dialog: Dialog | null = null
  let loaded_run: TaskRun | null = null
  let loaded_task: Task | null = null
  let loading_run = false
  let run_load_error: KilnError | null = null

  export function show(
    kiln_task_tool_data: {
      tool_id: string
      task_run_id: string
      project_id: string
      task_id: string
    } | null,
  ) {
    load_tool_messages_dialog_data(kiln_task_tool_data)
    dialog?.show()
  }

  async function load_tool_messages_dialog_data(
    kiln_task_tool_data: {
      tool_id: string
      task_run_id: string
      project_id: string
      task_id: string
    } | null,
  ) {
    loaded_run = null
    loaded_task = null
    run_load_error = null

    if (kiln_task_tool_data) {
      const project_id = kiln_task_tool_data.project_id
      const task_id = kiln_task_tool_data.task_id
      const run_id = kiln_task_tool_data.task_run_id

      try {
        loading_run = true

        // Load both run and task data in parallel
        const [run_response, task_response] = await Promise.all([
          client.GET(
            "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}",
            {
              params: {
                path: { project_id, task_id, run_id },
              },
            },
          ),
          client.GET("/api/projects/{project_id}/tasks/{task_id}", {
            params: {
              path: { project_id, task_id },
            },
          }),
        ])

        if (run_response.error) {
          throw run_response.error
        }
        if (task_response.error) {
          throw task_response.error
        }

        loaded_run = run_response.data
        loaded_task = task_response.data
      } catch (error) {
        run_load_error = createKilnError(error)
        loaded_run = null
        loaded_task = null
      } finally {
        loading_run = false
      }
    } else {
      run_load_error = createKilnError(new Error("No tool data found"))
    }
  }
</script>

<Dialog title={"Tool Run"} bind:this={dialog} width="wide">
  <div>
    <div class="font-bold mt-6 mb-2 flex items-center justify-between">
      <span>All Messages</span>
      <div class="font-normal">
        <InfoTooltip
          tooltip_text={loaded_task
            ? `The full Dataset Run can be viewed in the Dataset tab for the task the tool invoked: ${loaded_task.name} (ID: ${loaded_task.id})`
            : "The full Dataset Run can be viewed in the Dataset tab for the task the tool invoked."}
          position="bottom"
        />
      </div>
    </div>
    {#if loading_run}
      <div class="flex justify-center items-center py-8">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if run_load_error}
      <div class="text-error py-4">
        Error loading run: {run_load_error.getMessage()}
      </div>
    {:else if loaded_run && loaded_run.trace}
      <div class="overflow-y-auto">
        <TraceComponent trace={loaded_run.trace} {project_id} />
      </div>
    {:else}
      <div class="text-gray-500 py-4">No run data available</div>
    {/if}
  </div>
</Dialog>
