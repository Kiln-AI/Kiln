<script lang="ts">
  import { onMount } from "svelte"
  import Warning from "$lib/ui/warning.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import {
    getConfig,
    updateConfig,
    deleteConfig,
    testAccess,
    isGitHubUrl,
    isGitLabUrl,
    gitHubPatDeepLink,
    gitLabPatDeepLink,
    type GitSyncConfigResponse,
  } from "$lib/git_sync/api"

  export let project_id: string

  let config: GitSyncConfigResponse | null = null
  let loading = true
  let error: KilnError | null = null
  let show_auth_form = false
  let new_pat_token = ""
  let saving_token = false
  let token_error: KilnError | null = null
  let removing = false
  let disable_dialog: Dialog

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
      show_auth_form = false
      new_pat_token = ""
    } catch (e) {
      token_error = createKilnError(e)
    } finally {
      saving_token = false
    }
  }

  async function disable_sync(): Promise<boolean> {
    try {
      removing = true
      error = null
      await deleteConfig(project_id)
      config = null
      return true
    } catch (e) {
      error = createKilnError(e)
      return false
    } finally {
      removing = false
    }
  }

  $: is_github = config?.git_url ? isGitHubUrl(config.git_url) : false
  $: is_gitlab = config?.git_url ? isGitLabUrl(config.git_url) : false
  $: is_system_keys = config?.auth_mode === "system_keys"
</script>

{#if loading}
  <div class="flex items-center gap-2 py-2">
    <span class="loading loading-spinner loading-sm"></span>
    <span class="text-sm text-gray-500">Loading sync status...</span>
  </div>
{:else if config}
  <div class="border rounded-lg p-4">
    <div class="flex items-center justify-between gap-4">
      <div class="min-w-0">
        <h3 class="text-sm font-medium">Git Sync</h3>
        <p class="text-xs text-gray-500 mt-1">
          Syncing with <span class="font-medium">{config.branch}</span> branch
        </p>
        {#if config.git_url}
          <p class="text-xs text-gray-400 mt-0.5 truncate max-w-sm">
            {config.git_url}
          </p>
        {/if}
      </div>
      <div class="flex flex-col gap-1.5 flex-shrink-0">
        <button
          class="btn btn-sm btn-ghost"
          on:click={() => disable_dialog.show()}
        >
          Disable
        </button>
        <button
          class="btn btn-sm btn-ghost"
          on:click={() => {
            show_auth_form = !show_auth_form
            token_error = null
          }}
        >
          {show_auth_form ? "Cancel" : "Update Auth"}
        </button>
      </div>
    </div>

    {#if show_auth_form}
      <div class="mt-3 border-t pt-3">
        {#if is_system_keys}
          <Warning
            warning_message="This repo was connected via system SSH keys. Either fix your SSH key connection to your git provider, or remove this project and re-add it with another auth mechanism like tokens."
            warning_color="warning"
          />
        {:else}
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
          {:else if is_gitlab && config?.git_url}
            <div class="text-xs text-gray-500 mt-1">
              <a
                href={gitLabPatDeepLink(config.git_url)}
                target="_blank"
                rel="noopener noreferrer"
                class="link text-primary"
              >
                Generate a GitLab token</a
              >. Set expiration to at least 1 year.
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

<Dialog
  bind:this={disable_dialog}
  title="Remove Git Connection"
  action_buttons={[
    {
      label: "Delete",
      isError: true,
      asyncAction: disable_sync,
      loading: removing,
    },
    {
      label: "Cancel",
      isCancel: true,
    },
  ]}
>
  <p class="text-sm">
    Connection will be removed and sync will no longer work. You'll need to
    reconnect to re-establish sync.
  </p>
</Dialog>
