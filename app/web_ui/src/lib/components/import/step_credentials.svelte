<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Warning from "$lib/ui/warning.svelte"
  import { testAccess, isGitHubUrl, gitHubPatDeepLink } from "$lib/git_sync/api"

  export let git_url: string
  export let initial_token: string | null = null
  export let on_success: (token: string, auth_method: string) => void

  let pat_token = initial_token || ""
  let error: KilnError | null = null
  let submitting = false
  let saved = false

  $: is_github = isGitHubUrl(git_url)

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
</script>

<h2 class="text-xl font-medium mb-2">Authentication</h2>
<p class="text-sm text-gray-500 mb-6">
  This repository requires authentication. Enter a Personal Access Token (PAT)
  with read and write access to the repository.
</p>

<FormContainer
  submit_label="Verify Token"
  on:submit={test_and_save}
  bind:submitting
  bind:error
  bind:saved
  focus_on_mount={true}
>
  {#if is_github}
    <div class="text-sm">
      <a
        href={gitHubPatDeepLink()}
        target="_blank"
        rel="noopener noreferrer"
        class="link text-primary"
      >
        Generate a GitHub token</a
      > and paste it below. It must have read/write access to the selected repo.
    </div>
  {:else}
    <Warning
      warning_message="Generate an access token following instructions from your Git hosting provider (GitLab, Bitbucket, etc). The process varies from host to host."
      warning_color="gray"
      warning_icon="info"
    />
  {/if}

  <div class="form-control w-full">
    <label class="label" for="pat_token">
      <span class="label-text">Personal Access Token</span>
    </label>
    <input
      id="pat_token"
      type="password"
      class="input input-bordered w-full"
      bind:value={pat_token}
      placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
      autocomplete="off"
    />
  </div>
</FormContainer>
