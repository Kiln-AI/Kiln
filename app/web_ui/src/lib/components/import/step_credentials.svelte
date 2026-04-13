<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import MarkdownBlock from "$lib/ui/markdown_block.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import {
    testAccess,
    isGitHubUrl,
    isGitLabUrl,
    gitHubPatDeepLink,
    gitLabPatDeepLink,
    gitOwnerFromUrl,
    type OAuthStartResponse,
  } from "$lib/git_sync/api"
  import {
    startOAuthFlow,
    type OAuthFlowCallbacks,
  } from "$lib/git_sync/oauth_flow"
  import { onDestroy } from "svelte"

  export let git_url: string
  export let initial_token: string | null = null
  export let on_success: (token: string, auth_method: string) => void

  $: is_github = isGitHubUrl(git_url)
  $: is_gitlab = isGitLabUrl(git_url)

  let mode: "oauth" | "pat" = isGitHubUrl(git_url) ? "oauth" : "pat"
  let pat_token = initial_token || ""
  let error: KilnError | null = null
  let submitting = false
  let saved = false

  // OAuth state
  let oauth_starting = false
  let oauth_error: string | null = null
  let cancel_oauth: (() => void) | null = null
  let start_response: OAuthStartResponse | null = null
  let oauth_generation = 0

  onDestroy(() => {
    if (cancel_oauth) {
      cancel_oauth()
      cancel_oauth = null
    }
  })

  function reset_oauth() {
    if (cancel_oauth) {
      cancel_oauth()
      cancel_oauth = null
    }
    oauth_starting = false
    oauth_error = null
    start_response = null
    oauth_generation++
  }

  function start_oauth() {
    // Open popup as the very first thing in the click handler so Safari
    // recognizes it as user-initiated. Pass it to startOAuthFlow.
    const popup = window.open("about:blank", "_blank")

    if (cancel_oauth) {
      cancel_oauth()
    }

    oauth_error = null
    oauth_starting = true
    start_response = null
    oauth_generation++
    const this_generation = oauth_generation

    const callbacks: OAuthFlowCallbacks = {
      onStarted: (response: OAuthStartResponse) => {
        if (this_generation !== oauth_generation) return
        start_response = response
        oauth_starting = false
      },
      onPolling: () => {
        if (this_generation !== oauth_generation) return
      },
      onSuccess: async (token: string) => {
        if (this_generation !== oauth_generation) return
        try {
          const result = await testAccess(git_url, null, "github_oauth", token)
          if (this_generation !== oauth_generation) return
          if (result.success) {
            on_success(token, "github_oauth")
          } else {
            oauth_error =
              result.message ||
              "The GitHub App does not have access to this repository. Please ensure the app is installed on the correct organization and repository, then try again."
          }
        } catch (e) {
          if (this_generation !== oauth_generation) return
          oauth_error =
            e instanceof Error ? e.message : "Failed to verify access"
        }
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

  async function test_and_save() {
    try {
      error = null
      submitting = true

      if (!pat_token.trim()) {
        error = new KilnError("A personal access token is required")
        return
      }

      const result = await testAccess(git_url, pat_token)

      if (result.success) {
        on_success(pat_token, result.auth_method || "pat_token")
      } else {
        error = new KilnError(result.message)
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }

  function hint_text(is_error: boolean): string {
    const prefix = is_error ? "**Authentication failed.**\n" : ""

    if (is_github) {
      const owner = gitOwnerFromUrl(git_url)
      const owner_hint = owner
        ? `Be sure to set Resource Owner to "${owner}".`
        : "Be sure to set Resource Owner to the owner of this repository."
      return `${prefix}${owner_hint}\nThe token must have read/write access to the repo. Select "Contents"=write in Permissions.`
    }

    if (is_gitlab) {
      return `${prefix}The token must have read/write access to the repo.\nExtend the default expiration so you don't have to re-enter it later.`
    }

    return `${prefix}The token must have read/write access to the repository.`
  }

  $: token_link = is_github
    ? gitHubPatDeepLink()
    : is_gitlab
      ? gitLabPatDeepLink(git_url)
      : null

  $: token_link_label = is_github
    ? "Generate token on GitHub"
    : is_gitlab
      ? "Generate token on GitLab"
      : null

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

<h2 class="text-xl font-medium mb-2">Authentication</h2>

{#if is_github && mode === "oauth"}
  <p class="text-sm text-gray-500 mb-6">
    Connect your GitHub account to grant Kiln access to this repository.
  </p>

  {#if oauth_error}
    <div class="mb-4">
      <Warning warning_message={oauth_error} warning_color="error" />
    </div>
  {/if}

  {#if start_response && !oauth_error}
    <div class="flex flex-col items-center py-8 gap-4">
      <span class="loading loading-spinner loading-lg text-primary"></span>
      <p class="text-sm text-gray-500">Waiting for GitHub authorization...</p>
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
          class="text-sm text-gray-500 hover:text-gray-700 underline"
        >
          Already have the app installed? Authorize directly
        </a>
      {/if}
      <button class="btn btn-sm btn-ghost mt-2" on:click={reset_oauth}>
        Cancel
      </button>
    </div>
  {:else}
    <button
      class="btn btn-primary w-full"
      on:click={start_oauth}
      disabled={oauth_starting}
    >
      {#if oauth_starting}
        <span class="loading loading-spinner loading-sm"></span>
      {/if}
      {oauth_error ? "Retry with GitHub" : "Connect with GitHub"}
    </button>
  {/if}

  <div class="mt-4 text-center">
    <button
      class="btn btn-link btn-sm text-gray-500 no-underline hover:text-gray-700 hover:underline focus-visible:underline"
      on:click={() => {
        mode = "pat"
        reset_oauth()
      }}
    >
      or use a Personal Access Token
    </button>
  </div>
{:else}
  {#if is_github}
    <p class="text-sm text-gray-500 mb-6">
      Generate a fine-grained personal access token on GitHub, then paste it
      below.
    </p>
  {:else if is_gitlab}
    <p class="text-sm text-gray-500 mb-6">
      Generate a personal access token on GitLab with read/write repo access,
      then paste it below. Extend the default expiration so you don't have to
      re-enter it later.
    </p>
  {:else}
    <p class="text-sm text-gray-500 mb-6">
      Generate an access token from your Git hosting provider and paste it
      below.
    </p>
  {/if}

  <FormContainer
    submit_label="Verify Token"
    submit_disabled={!pat_token.trim()}
    on:submit={test_and_save}
    bind:submitting
    bind:error
    bind:saved
    focus_on_mount={true}
  >
    <div
      class="border rounded-lg px-4 py-3 flex flex-row items-start gap-3 {error
        ? 'border-error bg-error/5'
        : 'border-base-200'}"
    >
      <svg
        class="w-5 h-5 flex-none mt-0.5 {error ? 'text-error' : 'text-primary'}"
        fill="currentColor"
        viewBox="0 0 256 256"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M128,20.00012a108,108,0,1,0,108,108A108.12217,108.12217,0,0,0,128,20.00012Zm0,192a84,84,0,1,1,84-84A84.0953,84.0953,0,0,1,128,212.00012Zm-12-80v-52a12,12,0,1,1,24,0v52a12,12,0,1,1-24,0Zm28,40a16,16,0,1,1-16-16A16.018,16.018,0,0,1,144,172.00012Z"
        />
      </svg>
      <div class="text-sm text-gray-500 flex flex-col gap-2">
        <MarkdownBlock markdown_text={hint_text(!!error)} />
        {#if token_link && token_link_label}
          <a
            href={token_link}
            target="_blank"
            rel="noopener noreferrer"
            class="link text-primary font-medium"
          >
            {error ? `Generate a new token →` : `${token_link_label} →`}
          </a>
        {/if}
      </div>
    </div>

    <FormElement
      label="Personal Access Token"
      id="pat_token"
      inputType="input"
      bind:value={pat_token}
      placeholder={is_gitlab
        ? "glpat-xxxxxxxxxxxxxxxxxxxx"
        : is_github
          ? "ghp_xxxxxxxxxxxxxxxxxxxx"
          : "Access token"}
    />
  </FormContainer>

  {#if is_github}
    <div class="mt-4 text-center">
      <button
        class="btn btn-link btn-sm text-gray-500 no-underline hover:text-gray-700 hover:underline focus-visible:underline"
        on:click={() => {
          mode = "oauth"
          error = null
        }}
      >
        or connect with GitHub
      </button>
    </div>
  {/if}
{/if}
