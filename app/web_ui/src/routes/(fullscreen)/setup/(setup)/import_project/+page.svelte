<script lang="ts">
  import ImportProject from "$lib/components/import/import_project.svelte"
  import { goto } from "$app/navigation"
  import { client } from "$lib/api_client"

  async function handle_complete(project_id: string) {
    const should_skip_task_creation = await project_has_tasks(project_id)

    if (should_skip_task_creation) {
      goto("/setup/select_task")
    } else {
      goto("/setup/create_task/" + project_id)
    }
  }

  async function project_has_tasks(project_id: string): Promise<boolean> {
    try {
      const { data: tasks_data, error: tasks_error } = await client.GET(
        "/api/projects/{project_id}/tasks",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )

      if (tasks_error) {
        return false
      }

      return tasks_data && tasks_data.length > 0
    } catch (_) {
      return false
    }
  }
</script>

<div class="grow"></div>
<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center">
  Import Project
</h1>
<h3 class="text-base font-medium text-center mt-3 max-w-[600px] mx-auto">
  Import an existing Kiln project
</h3>

<div
  class="flex-none min-h-[50vh] px-4 h-full flex flex-col py-18 mx-auto w-full max-w-[600px]"
>
  <ImportProject
    create_link="/setup/create_project"
    on_complete={handle_complete}
  />
</div>

<div class="grow-[1.5]"></div>
