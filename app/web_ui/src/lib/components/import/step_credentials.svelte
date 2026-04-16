<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import MarkdownBlock from "$lib/ui/markdown_block.svelte"
  import {
    testAccess,
    isGitHubUrl,
    isGitLabUrl,
    gitHubPatDeepLink,
    gitLabPatDeepLink,
    gitOwnerFromUrl,
    gitRepoNameFromUrl,
  } from "$lib/git_sync/api"

  export let git_url: string
  export let initial_token: string | null = null
  export let on_success: (token: string, auth_method: string) => void

  let pat_token = initial_token || ""
  let error: KilnError | null = null
  let submitting = false
  let saved = false

  $: is_github = isGitHubUrl(git_url)
  $: is_gitlab = isGitLabUrl(git_url)

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
      const owner = gitOwnerFromUrl(git_url)
      const repo_name = gitRepoNameFromUrl(git_url)
      const explainer =
        "The token must have read/write access to the selected repository:"
      const owner_hint = owner
        ? ` • Set "Resource Owner" to "${owner}"`
        : " • Set Resource Owner to the owner of this repository"
      const repo_hint = repo_name
        ? ` • "Repository access" must include "${repo_name}"`
        : ` • "Repository access" must include the name of this repository`
      const permissions_hint = ` • In Permissions add "Contents" permission set to "Read and write"`
      const expiration_hint = ` • Set "Expiration" to an appropriate value for your project`
      return `${prefix}${explainer}\n${owner_hint}\n${repo_hint}\n${permissions_hint}\n${expiration_hint}`
    }

    if (is_gitlab) {
      return `${prefix}The token must have read/write access to the repo.\nExtend the default expiration so you don't have to re-enter it later.`
    }

    return `${prefix}The token must have read/write access to the repository.`
  }

  $: token_link = is_github
    ? gitHubPatDeepLink(git_url)
    : is_gitlab
      ? gitLabPatDeepLink(git_url)
      : null

  $: token_link_label = is_github
    ? "Generate token on GitHub"
    : is_gitlab
      ? "Generate token on GitLab"
      : null
</script>

<h2 class="text-xl font-medium mb-2">Authentication</h2>

{#if is_github}
  <p class="text-sm text-gray-500 mb-6">
    Generate a fine-grained personal access token on GitHub, then paste it
    below.
  </p>
{:else if is_gitlab}
  <p class="text-sm text-gray-500 mb-6">
    Generate a personal access token on GitLab with read/write repo access, then
    paste it below. Extend the default expiration so you don't have to re-enter
    it later.
  </p>
{:else}
  <p class="text-sm text-gray-500 mb-6">
    Generate an access token from your Git hosting provider and paste it below.
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
