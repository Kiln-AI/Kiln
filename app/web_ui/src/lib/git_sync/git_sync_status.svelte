<script lang="ts">
  import { onMount, onDestroy } from "svelte"
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
  let oauth_starting = false
  let oauth_error: string | null = null
  let cancel_oauth: (() => void) | null = null
  let oauth_generation = 0

  // Two-step state
  let oauth_token: string | null = null
  let install_url: string | null = null
  let needs_install = false
  let checking_access = false
  let install_clicked = false

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
    oauth_starting = false
    oauth_error = null
    oauth_token = null
    install_url = null
    needs_install = false
    checking_access = false
    install_clicked = false
    oauth_generation++
  }

  function open_install() {
    if (!install_url) return
    window.open(install_url, "_blank", "noopener,noreferrer")
    install_clicked = true
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

  async function check_access_and_save(token: string, generation: number) {
    checking_access = true
    const git_url = config!.git_url!
    try {
      const result = await testAccess(git_url, null, "github_oauth", token)
      if (generation !== oauth_generation) return
      if (result.success) {
        config = await updateConfig(project_id, buildOAuthUpdatePayload(token))
        close_auth_form()
      } else {
        oauth_token = token
        needs_install = true
      }
    } catch (e) {
      if (generation !== oauth_generation) return
      oauth_error = e instanceof Error ? e.message : "Failed to verify access"
    } finally {
      if (generation === oauth_generation) {
        checking_access = false
      }
    }
  }

  function start_oauth() {
    if (!config?.git_url) return

    const popup = window.open("about:blank", "_blank")

    if (cancel_oauth) {
      cancel_oauth()
    }

    oauth_error = null
    oauth_starting = true
    needs_install = false
    oauth_token = null
    install_url = null
    oauth_generation++
    const this_generation = oauth_generation
    const git_url = config.git_url

    const callbacks: OAuthFlowCallbacks = {
      onStarted: (response) => {
        if (this_generation !== oauth_generation) return
        install_url = response.install_url
        oauth_starting = false
      },
      onPolling: () => {
        if (this_generation !== oauth_generation) return
      },
      onSuccess: (token: string) => {
        if (this_generation !== oauth_generation) return
        check_access_and_save(token, this_generation)
      },
      onError: (err: string) => {
        if (this_generation !== oauth_generation) return
        oauth_starting = false
        oauth_error = err
      },
    }

    const handle = startOAuthFlow(git_url, callbacks, popup)
    cancel_oauth = handle.cancel
  }

  async function retry_access_check() {
    if (!oauth_token) return
    oauth_error = null
    oauth_generation++
    await check_access_and_save(oauth_token, oauth_generation)
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
          {#if needs_install && oauth_token}
            <div class="flex flex-col items-center py-4 gap-3">
              <div
                class="w-10 h-10 rounded-full bg-success/10 flex items-center justify-center"
              >
                <svg
                  class="w-5 h-5 text-success"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke-width="2"
                  stroke="currentColor"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    d="M4.5 12.75l6 6 9-13.5"
                  />
                </svg>
              </div>
              <p class="text-xs font-medium">Authorized</p>

              <div class="w-full border-t border-base-200 my-1"></div>

              <p class="text-sm font-medium">Install App on Repository</p>
              <p class="text-xs text-gray-500 text-center">
                Install the Kiln Sync GitHub App on the repository, then verify
                access.
              </p>
              <button
                class="btn w-full {install_clicked
                  ? 'btn-xs btn-ghost'
                  : 'btn-primary btn-sm'}"
                on:click={open_install}
              >
                {install_clicked
                  ? "Retry Install on GitHub"
                  : "Install Kiln Sync on GitHub"}
              </button>
              <button
                class="btn w-full {install_clicked
                  ? 'btn-primary btn-sm'
                  : 'btn-xs btn-ghost'}"
                on:click={retry_access_check}
                disabled={checking_access}
              >
                {#if checking_access}
                  <span class="loading loading-spinner loading-xs"></span>
                {/if}
                Verify Access
              </button>
              {#if oauth_error}
                <div class="w-full">
                  <Warning
                    warning_message={oauth_error}
                    warning_color="error"
                  />
                </div>
              {/if}
              <button
                class="btn btn-link btn-xs text-gray-500 no-underline hover:text-gray-700 hover:underline focus-visible:underline"
                on:click={reset_oauth}
              >
                Start over
              </button>
            </div>
          {:else}
            {#if oauth_error}
              <div class="mb-3">
                <Warning warning_message={oauth_error} warning_color="error" />
              </div>
            {/if}

            {#if (oauth_starting || checking_access) && !oauth_error}
              <div class="flex flex-col items-center py-6 gap-3">
                <span class="loading loading-spinner loading-md text-primary"
                ></span>
                <p class="text-sm text-gray-500">
                  {checking_access
                    ? "Verifying access..."
                    : "Waiting for GitHub authorization..."}
                </p>
                <button
                  class="btn btn-sm btn-ghost mt-1"
                  on:click={reset_oauth}
                >
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
                  class="btn btn-link btn-xs text-gray-500 no-underline hover:text-gray-700 hover:underline focus-visible:underline"
                  on:click={() => {
                    mode = "pat"
                    reset_oauth()
                  }}
                >
                  or use a Personal Access Token
                </button>
              </div>
            {/if}
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
                class="btn btn-link btn-xs text-gray-500 no-underline hover:text-gray-700 hover:underline focus-visible:underline"
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
