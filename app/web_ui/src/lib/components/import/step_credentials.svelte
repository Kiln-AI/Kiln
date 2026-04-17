<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import MarkdownBlock from "$lib/ui/markdown_block.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import {
    testAccess,
    isGitHubUrl,
    isGitLabUrl,
    gitHubClassicPatDeepLink,
    gitHubFineGrainedPatDeepLink,
    gitLabPatDeepLink,
    gitOwnerFromUrl,
    gitRepoNameFromUrl,
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
  let oauth_generation = 0

  // Two-step state: after OAuth succeeds, we may need to install the app
  let oauth_token: string | null = null
  let install_url: string | null = null
  let needs_install = false
  let checking_access = false
  let install_clicked = false

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
    oauth_token = null
    install_url = null
    needs_install = false
    checking_access = false
    install_clicked = false
    oauth_generation++
  }

  function open_install() {
    if (!install_url) return
    // Open window first so popup blockers don't block it.
    window.open(install_url, "_blank", "noopener,noreferrer")
    install_clicked = true
  }

  async function check_access_with_token(token: string, generation: number) {
    checking_access = true
    try {
      const result = await testAccess(git_url, null, "github_oauth", token)
      if (generation !== oauth_generation) return
      if (result.success) {
        on_success(token, "github_oauth")
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
        check_access_with_token(token, this_generation)
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
    await check_access_with_token(oauth_token, oauth_generation)
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
    let prefix = is_error ? "**Authentication failed.**\n" : ""

    if (is_github) {
      if (is_error) {
        prefix =
          "**Authentication Failed - Create a New Token Following These Instructions**\n"
      }
      const explainer =
        "Create a classic personal access token with the following settings:"
      const scope_hint = ` • Select the **repo** scope. Read/write access to your repos are required.`
      const expiration_hint = ` • Set **Expiration** to an appropriate value for your project.`
      return `${prefix}${explainer}\n${scope_hint}\n${expiration_hint}`
    }

    if (is_gitlab) {
      return `${prefix}The token must have read/write access to the repo.\nExtend the default expiration so you don't have to re-enter it later.`
    }

    return `${prefix}The token must have read/write access to the repository.`
  }

  $: token_link = is_github
    ? gitHubClassicPatDeepLink(git_url)
    : is_gitlab
      ? gitLabPatDeepLink(git_url)
      : null

  $: fine_grained_link = is_github
    ? gitHubFineGrainedPatDeepLink(git_url)
    : null

  $: fine_grained_tooltip = (() => {
    const owner = gitOwnerFromUrl(git_url)
    const repo_name = gitRepoNameFromUrl(git_url)
    const owner_hint = owner
      ? `Set "Resource Owner" to "${owner}"`
      : "Set Resource Owner to the owner of this repository"
    const repo_hint = repo_name
      ? `"Repository access" must include "${repo_name}"`
      : `"Repository access" must include the name of this repository`
    const permissions_hint = `In Permissions add "Contents" permission set to "Read and write"`
    const expiration_hint = `Set "Expiration" to an appropriate value`
    const footer =
      "**While it will provide you a token, it may not work until an org admin approves it.**"
    return `**Fine-grained token setup:**\n • ${owner_hint}\n • ${repo_hint}\n • ${permissions_hint}\n • ${expiration_hint}\n${footer}`
  })()

  $: token_link_label = is_github
    ? "Generate token on GitHub"
    : is_gitlab
      ? "Generate token on GitLab"
      : null
</script>

<h2 class="text-xl font-medium mb-2">Authentication</h2>

{#if is_github && mode === "oauth"}
  {#if needs_install && oauth_token}
    <p class="text-sm text-gray-500 mb-6">
      GitHub account connected. Now install the Kiln Sync app on the repository
      to grant access.
    </p>

    <div class="flex flex-col items-center py-4 gap-4">
      <div
        class="w-12 h-12 rounded-full bg-success/10 flex items-center justify-center"
      >
        <svg
          class="w-6 h-6 text-success"
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
      <p class="text-sm font-medium">Step 1: Authorized</p>

      <div class="w-full border-t border-base-200 my-2"></div>

      <p class="text-sm font-medium">Step 2: Install App on Repository</p>
      <p class="text-sm text-gray-500 text-center max-w-sm">
        The Kiln Sync GitHub App needs to be installed on the repository to
        enable syncing. Click below to install it, then come back and verify.
      </p>
      <button
        class="btn w-full max-w-sm {install_clicked
          ? 'btn-sm btn-ghost'
          : 'btn-primary'}"
        on:click={open_install}
      >
        {install_clicked
          ? "Retry Install on GitHub"
          : "Install Kiln Sync on GitHub"}
      </button>
      <button
        class="btn w-full max-w-sm {install_clicked
          ? 'btn-primary'
          : 'btn-sm btn-ghost'}"
        on:click={retry_access_check}
        disabled={checking_access}
      >
        {#if checking_access}
          <span class="loading loading-spinner loading-xs"></span>
        {/if}
        Verify Access
      </button>
      {#if oauth_error}
        <div class="w-full max-w-sm">
          <Warning warning_message={oauth_error} warning_color="error" />
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
    <p class="text-sm text-gray-500 mb-6">
      Connect your GitHub account to grant Kiln access to this repository.
    </p>

    {#if oauth_error}
      <div class="mb-4">
        <Warning warning_message={oauth_error} warning_color="error" />
      </div>
    {/if}

    {#if (oauth_starting || checking_access) && !oauth_error}
      <div class="flex flex-col items-center py-8 gap-4">
        <span class="loading loading-spinner loading-lg text-primary"></span>
        <p class="text-sm text-gray-500">
          {checking_access
            ? "Verifying access..."
            : "Waiting for GitHub authorization..."}
        </p>
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
  {/if}
{:else}
  {#if is_github}
    <p class="text-sm text-gray-500 mb-6">
      Generate a classic personal access token on GitHub, then paste it below.
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
        {#if fine_grained_link}
          <p class="text-xs text-gray-400">
            You can also use <a
              href={fine_grained_link}
              target="_blank"
              rel="noopener noreferrer"
              class="link">fine-grained access tokens</a
            >, however they are harder to setup and may require approval by an
            org administrator.<InfoTooltip
              tooltip_text={fine_grained_tooltip}
              no_pad
            />
          </p>
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
