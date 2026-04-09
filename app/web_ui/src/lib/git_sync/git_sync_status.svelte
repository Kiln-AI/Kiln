<script lang="ts">
  import { onMount } from "svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import {
    getConfig,
    updateConfig,
    deleteConfig,
    testAccess,
    isGitHubUrl,
    gitHubPatDeepLink,
    type GitSyncConfigResponse,
  } from "$lib/git_sync/api"

  export let project_id: string

  let config: GitSyncConfigResponse | null = null
  let loading = true
  let error: KilnError | null = null
  let toggling = false
  let show_token_form = false
  let new_pat_token = ""
  let saving_token = false
  let token_error: KilnError | null = null
  let removing = false

  onMount(async () => {
    await load_config()
  })

  async function load_config() {
    try {
      loading = true
      error = null
      config = await getConfig(project_id)
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  async function toggle_mode() {
    if (!config) return
    try {
      toggling = true
      error = null
      const new_mode = config.sync_mode === "auto" ? "manual" : "auto"
      config = await updateConfig(project_id, { sync_mode: new_mode })
    } catch (e) {
      error = createKilnError(e)
    } finally {
      toggling = false
    }
  }

  async function save_token() {
    if (!config || !new_pat_token.trim()) return
    try {
      saving_token = true
      token_error = null

      if (config.git_url) {
        const result = await testAccess(config.git_url, new_pat_token)
        if (!result.success) {
          token_error = new KilnError(result.message)
          return
        }
      }

      config = await updateConfig(project_id, { pat_token: new_pat_token })
      show_token_form = false
      new_pat_token = ""
    } catch (e) {
      token_error = createKilnError(e)
    } finally {
      saving_token = false
    }
  }

  async function remove_sync() {
    if (
      !confirm(
        "Are you sure you want to remove git sync for this project? This will disable automatic syncing.",
      )
    )
      return
    try {
      removing = true
      error = null
      await deleteConfig(project_id)
      config = null
    } catch (e) {
      error = createKilnError(e)
    } finally {
      removing = false
    }
  }

  $: is_github = config?.git_url ? isGitHubUrl(config.git_url) : false
</script>

{#if loading}
  <div class="flex items-center gap-2 py-2">
    <span class="loading loading-spinner loading-sm"></span>
    <span class="text-sm text-gray-500">Loading sync status...</span>
  </div>
{:else if config}
  <div class="border rounded-lg p-4">
    <div class="flex items-center justify-between">
      <div>
        <h3 class="text-sm font-medium">Git Sync</h3>
        <p class="text-xs text-gray-500 mt-1">
          {#if config.sync_mode === "auto"}
            Auto-syncing with <span class="font-medium">{config.branch}</span> branch
          {:else}
            Manual mode (sync disabled)
          {/if}
        </p>
        {#if config.git_url}
          <p class="text-xs text-gray-400 mt-0.5 truncate max-w-sm">
            {config.git_url}
          </p>
        {/if}
      </div>
      <div class="flex items-center gap-3">
        {#if config.sync_mode === "auto"}
          <span class="badge badge-success badge-sm">Active</span>
        {:else}
          <span class="badge badge-sm">Disabled</span>
        {/if}
        <button
          class="btn btn-sm btn-ghost"
          on:click={toggle_mode}
          disabled={toggling}
        >
          {#if toggling}
            <span class="loading loading-spinner loading-xs"></span>
          {:else}
            {config.sync_mode === "auto" ? "Disable" : "Enable"}
          {/if}
        </button>
      </div>
    </div>

    <div class="flex gap-2 mt-3 border-t pt-3">
      <button
        class="btn btn-xs btn-ghost"
        on:click={() => {
          show_token_form = !show_token_form
          token_error = null
        }}
      >
        {show_token_form ? "Cancel" : "Update Token"}
      </button>
      <button
        class="btn btn-xs btn-ghost text-error"
        on:click={remove_sync}
        disabled={removing}
      >
        {#if removing}
          <span class="loading loading-spinner loading-xs"></span>
        {:else}
          Remove Sync
        {/if}
      </button>
    </div>

    {#if show_token_form}
      <div class="mt-3 border-t pt-3">
        <label class="label" for="update_pat">
          <span class="label-text text-sm">New Personal Access Token</span>
        </label>
        <div class="flex gap-2">
          <input
            id="update_pat"
            type="password"
            class="input input-bordered input-sm flex-1"
            bind:value={new_pat_token}
            placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
          />
          <button
            class="btn btn-sm btn-primary"
            on:click={save_token}
            disabled={saving_token || !new_pat_token.trim()}
          >
            {#if saving_token}
              <span class="loading loading-spinner loading-xs"></span>
            {:else}
              Save
            {/if}
          </button>
        </div>
        {#if is_github}
          <div class="text-xs text-gray-500 mt-1">
            <a
              href={gitHubPatDeepLink()}
              target="_blank"
              rel="noopener noreferrer"
              class="link text-primary"
            >
              Generate a GitHub token</a
            >. It must have read/write access to the selected repo.
          </div>
        {/if}
        {#if token_error}
          <div class="mt-2">
            <Warning
              warning_message={token_error.getMessage()}
              warning_color="error"
            />
          </div>
        {/if}
      </div>
    {/if}
  </div>

  {#if error}
    <div class="mt-2">
      <Warning warning_message={error.getMessage()} warning_color="error" />
    </div>
  {/if}
{/if}
