<script lang="ts">
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Warning from "$lib/ui/warning.svelte"
  import { saveConfig } from "$lib/git_sync/api"
  import { load_projects } from "$lib/stores"
  import { onMount } from "svelte"

  export let git_url: string
  export let pat_token: string | null
  export let clone_path: string
  export let branch: string
  export let project_path: string
  export let project_id: string
  export let project_name: string
  export let on_complete: (project_id: string) => void
  export let on_back: () => void

  let saving = true
  let error: KilnError | null = null
  let done = false

  onMount(async () => {
    try {
      await saveConfig({
        project_id: project_id,
        git_url: git_url,
        clone_path: clone_path,
        branch: branch,
        pat_token: pat_token,
        sync_mode: "auto",
      })

      await load_projects()
      done = true
    } catch (e) {
      error = createKilnError(e)
    } finally {
      saving = false
    }
  })
</script>

{#if saving}
  <div class="flex flex-col items-center py-12 gap-4">
    <span class="loading loading-spinner loading-lg"></span>
    <p class="text-sm text-gray-500">Saving configuration...</p>
  </div>
{:else if error}
  <h2 class="text-xl font-medium mb-2">Setup Error</h2>
  <Warning warning_message={error.getMessage()} warning_color="error" />
  <div class="mt-6">
    <button class="btn btn-primary" on:click={on_back}> Back </button>
  </div>
{:else if done}
  <div class="flex flex-col items-center py-8 gap-4">
    <div class="text-success">
      <svg
        class="w-16 h-16"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M16 9L10 15.5L7.5 13M12 21C16.9706 21 21 16.9706 21 12C21 7.02944 16.9706 3 12 3C7.02944 3 3 7.02944 3 12C3 16.9706 7.02944 21 12 21Z"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </div>

    <h2 class="text-xl font-medium">Git Sync Enabled</h2>

    <p class="text-sm text-gray-500 text-center max-w-md">
      Auto-sync is now active for "{project_name || project_path}". Changes will
      be automatically committed and pushed to the
      <span class="font-medium">{branch}</span> branch.
    </p>

    <div class="flex flex-row gap-4 mt-4">
      <button class="btn btn-primary" on:click={() => on_complete(project_id)}>
        Done
      </button>
    </div>
  </div>
{/if}
