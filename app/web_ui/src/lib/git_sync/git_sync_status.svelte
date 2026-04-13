<script lang="ts">
  import { onMount, onDestroy } from "svelte"
  import Warning from "$lib/ui/warning.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import MarkdownBlock from "$lib/ui/markdown_block.svelte"
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
    type OAuthStartResponse,
  } from "$lib/git_sync/api"
  import {
    startOAuthFlow,
    type OAuthFlowCallbacks,
  } from "$lib/git_sync/oauth_flow"
  import {
    initialAuthFormMode,
    buildOAuthUpdatePayload,
    buildPatUpdatePayload,
    type AuthFormMode,
  } from "$lib/git_sync/auth_form_mode"

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
  let mode: AuthFormMode = "pat"

  // OAuth state
  let oauth_polling = false
  let oauth_starting = false
  let oauth_error: string | null = null
  let cancel_oauth: (() => void) | null = null
  let start_response: OAuthStartResponse | null = null
  let oauth_generation = 0

  onMount(async () => {
    await load_config()
  })

  onDestroy(() => {
    if (cancel_oauth) {
      cancel_oauth()
      cancel_oauth = null
    }
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

  function reset_oauth() {
    if (cancel_oauth) {
      cancel_oauth()
      cancel_oauth = null
    }
    oauth_polling = false
    oauth_starting = false
    oauth_error = null
    start_response = null
    oauth_generation++
  }

  function open_auth_form() {
    show_auth_form = true
    token_error = null
    new_pat_token = ""
    mode = initialAuthFormMode(config?.auth_mode, config?.git_url)
    reset_oauth()
  }

  function close_auth_form() {
    show_auth_form = false
    token_error = null
    reset_oauth()
  }

  function start_oauth() {
    if (!config?.git_url) return

    // Open popup as the very first thing in the click handler so Safari
    // recognizes it as user-initiated. Pass it to startOAuthFlow.
    const popup = window.open("about:blank", "_blank")

    if (cancel_oauth) {
      cancel_oauth()
    }

    oauth_error = null
    oauth_starting = true
    oauth_polling = false
    start_response = null
    oauth_generation++
    const this_generation = oauth_generation
    const git_url = config.git_url

    const callbacks: OAuthFlowCallbacks = {
      onStarted: (response: OAuthStartResponse) => {
        if (this_generation !== oauth_generation) return
        start_response = response
        oauth_starting = false
      },
      onPolling: () => {
        if (this_generation !== oauth_generation) return
        oauth_polling = true
      },
      onSuccess: async (token: string) => {
        if (this_generation !== oauth_generation) return
        oauth_polling = false
        try {
          const result = await testAccess(git_url, null, "github_oauth", token)
          if (this_generation !== oauth_generation) return
          if (!result.success) {
            oauth_error =
              result.message ||
              "The GitHub App does not have access to this repository. Please ensure the app is installed on the correct organization and repository, then try again."
            return
          }
          config = await updateConfig(
            project_id,
            buildOAuthUpdatePayload(token),
          )
          close_auth_form()
        } catch (e) {
          if (this_generation !== oauth_generation) return
          oauth_error =
            e instanceof Error ? e.message : "Failed to verify access"
        }
      },
      onError: (err: string) => {
        if (this_generation !== oauth_generation) return
        oauth_polling = false
        oauth_starting = false
        oauth_error = err
      },
    }

    const handle = startOAuthFlow(git_url, callbacks, popup)
    cancel_oauth = handle.cancel
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

      config = await updateConfig(
        project_id,
        buildPatUpdatePayload(new_pat_token, config.auth_mode),
      )
      close_auth_form()
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
  $: is_github_oauth = config?.auth_mode === "github_oauth"

  $: needs_pre_selection_hint =
    start_response &&
    (!start_response.owner_pre_selected || !start_response.repo_pre_selected)

  $: pre_selection_hint_md = (() => {
    if (!start_response) return ""
    const hints = []
    if (!start_response.owner_pre_selected) {
      hints.push(`select the **${start_response.owner_name}** organization`)
    }
    if (!start_response.repo_pre_selected) {
      hints.push(`select the **${start_response.repo_name}** repository`)
    }
    return "Be sure to " + hints.join(" and ") + "."
  })()
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
            if (show_auth_form) {
              close_auth_form()
            } else {
              open_auth_form()
            }
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
        {:else if is_github && mode === "oauth"}
          {#if oauth_error}
            <div class="mb-3">
              <Warning warning_message={oauth_error} warning_color="error" />
            </div>
          {/if}

          {#if oauth_polling}
            <div class="flex flex-col items-center py-6 gap-3">
              <span class="loading loading-spinner loading-md text-primary"
              ></span>
              <p class="text-sm text-gray-500">
                Waiting for GitHub authorization...
              </p>
              {#if needs_pre_selection_hint && start_response}
                <div
                  class="border rounded-lg px-4 py-3 border-base-200 text-sm text-gray-500 max-w-md"
                >
                  <MarkdownBlock markdown_text={pre_selection_hint_md} />
                </div>
              {/if}
              {#if start_response?.authorize_url}
                <a
                  href={start_response.authorize_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-xs text-gray-400 hover:text-gray-600 underline"
                >
                  Already have the app installed? Authorize directly
                </a>
              {/if}
              <button class="btn btn-sm btn-ghost mt-1" on:click={reset_oauth}>
                Cancel
              </button>
            </div>
          {:else}
            <button
              class="btn btn-primary btn-sm w-full"
              on:click={start_oauth}
              disabled={oauth_starting}
            >
              {#if oauth_starting}
                <span class="loading loading-spinner loading-xs"></span>
              {/if}
              {#if oauth_error}
                Retry with GitHub
              {:else if is_github_oauth}
                Reconnect with GitHub
              {:else}
                Connect with GitHub
              {/if}
            </button>
            <div class="mt-3 text-center">
              <button
                class="btn btn-link btn-xs text-gray-400 no-underline hover:text-gray-600"
                on:click={() => {
                  mode = "pat"
                  reset_oauth()
                }}
              >
                or use a Personal Access Token
              </button>
            </div>
          {/if}
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
          {#if is_github}
            <div class="mt-3 text-center">
              <button
                class="btn btn-link btn-xs text-gray-400 no-underline hover:text-gray-600"
                on:click={() => {
                  mode = "oauth"
                  token_error = null
                }}
              >
                or connect with GitHub
              </button>
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
