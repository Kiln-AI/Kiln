<script lang="ts">
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Warning from "$lib/ui/warning.svelte"
  import {
    renameClone,
    saveConfig,
    is_stale_clone_error,
    isGitHubUrl,
    isGitLabUrl,
  } from "$lib/git_sync/api"
  import { clear_wizard_store } from "$lib/stores/git_import_wizard_store"
  import posthog from "posthog-js"
  import { load_projects } from "$lib/stores"
  import { onMount } from "svelte"

  export let git_url: string
  export let pat_token: string | null
  export let oauth_token: string | null = null
  export let auth_mode: string
  export let clone_path: string
  export let branch: string
  export let project_path: string
  export let project_id: string
  export let project_name: string
  export let on_complete: (project_id: string) => void
  export let on_back: () => void
  export let on_stale_clone: (() => void) | null = null

  let display_project_name = project_name
  let display_project_path = project_path
  let display_branch = branch
  let display_project_id = project_id

  let saving = true
  let error: KilnError | null = null
  let done = false

  function git_host_label(url: string): string {
    if (isGitHubUrl(url)) return "github"
    if (isGitLabUrl(url)) return "gitlab"
    return "other"
  }

  onMount(async () => {
    try {
      let final_clone_path = clone_path

      const rename_result = await renameClone(
        clone_path,
        project_name,
        project_id,
      )
      if (rename_result.success) {
        final_clone_path = rename_result.new_clone_path
        clone_path = final_clone_path
      } else {
        throw new Error(
          rename_result.message || "Failed to rename clone directory",
        )
      }

      await saveConfig({
        project_id: project_id,
        project_path: project_path,
        git_url: git_url,
        clone_path: final_clone_path,
        branch: branch,
        pat_token: pat_token,
        oauth_token: oauth_token,
        auth_mode: auth_mode,
        sync_mode: "auto",
      })

      posthog.capture("import_project", {
        method: "git_sync",
        git_host: git_host_label(git_url),
        auth_mode: auth_mode,
      })

      clear_wizard_store()

      try {
        await load_projects()
      } catch {
        // Non-fatal: config is already saved, project list will refresh on next navigation
      }
      done = true
    } catch (e) {
      if (is_stale_clone_error(e) && on_stale_clone) {
        on_stale_clone()
        return
      }
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

    <h2 class="text-xl font-medium">Git Auto Sync Enabled</h2>

    <p class="text-sm text-gray-500 text-center max-w-md">
      Auto-sync is now active for "{display_project_name ||
        display_project_path}". Changes will be automatically committed and
      pushed to the
      <span class="font-medium">{display_branch}</span> branch.
    </p>

    <div class="flex flex-row gap-4 mt-4">
      <button
        class="btn btn-primary btn-wide"
        on:click={() => on_complete(display_project_id)}
      >
        Done
      </button>
    </div>
  </div>
{/if}
