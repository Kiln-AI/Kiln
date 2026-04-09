<script lang="ts">
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Warning from "$lib/ui/warning.svelte"
  import { scanProjects, type ProjectInfo } from "$lib/git_sync/api"
  import { onMount } from "svelte"

  export let clone_path: string
  export let on_selected: (
    project_path: string,
    project_id: string,
    project_name: string,
  ) => void
  export let on_back: () => void

  let projects: ProjectInfo[] = []
  let loading = true
  let error: KilnError | null = null

  onMount(async () => {
    try {
      const result = await scanProjects(clone_path)
      projects = result.projects

      if (projects.length === 1) {
        select_project(projects[0])
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  })

  function select_project(project: ProjectInfo) {
    on_selected(project.path, project.id || project.name, project.name)
  }
</script>

<h2 class="text-xl font-medium mb-2">Select Project</h2>
<p class="text-sm text-gray-500 mb-6">
  Choose the Kiln project from this repository to sync.
</p>

{#if loading}
  <div class="flex justify-center py-8">
    <span class="loading loading-spinner loading-md"></span>
  </div>
{:else if error}
  <Warning warning_message={error.getMessage()} warning_color="error" />
  <div class="mt-4">
    <button class="btn btn-ghost btn-sm" on:click={on_back}>Back</button>
  </div>
{:else if projects.length === 0}
  <Warning
    warning_message="No Kiln project found in this repository. The repository must contain at least one project.kiln file."
    warning_color="error"
  />
  <div class="mt-4">
    <button class="btn btn-ghost btn-sm" on:click={on_back}>Back</button>
  </div>
{:else}
  <div class="space-y-2">
    {#each projects as project}
      <button
        class="w-full text-left p-4 border rounded-lg hover:border-primary hover:bg-base-200 transition-colors"
        on:click={() => select_project(project)}
      >
        <div class="font-medium">{project.name}</div>
        {#if project.description}
          <div class="text-sm text-gray-500 mt-1">{project.description}</div>
        {/if}
        <div class="text-xs text-gray-400 mt-1">{project.path}</div>
      </button>
    {/each}
  </div>

  <div class="mt-4">
    <button class="btn btn-ghost btn-sm" on:click={on_back}>Back</button>
  </div>
{/if}
