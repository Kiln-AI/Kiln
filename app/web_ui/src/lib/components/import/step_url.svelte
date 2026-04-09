<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { testAccess } from "$lib/git_sync/api"
  import { try_convert_ssh_to_https } from "$lib/git_sync/url_utils"

  export let initial_url: string = ""
  export let pat_token: string | null = null
  export let on_success: (url: string, auth_method: string) => void
  export let on_auth_required: (url: string) => void

  let git_url = initial_url
  let error: KilnError | null = null
  let submitting = false
  let saved = false
  let https_mode = false

  let ssh_fail_dialog: Dialog

  function is_ssh_url(url: string): boolean {
    return url.startsWith("git@") || url.startsWith("ssh://")
  }

  function switch_to_https() {
    https_mode = true
    git_url = try_convert_ssh_to_https(git_url)
    return true
  }

  async function check_access() {
    try {
      error = null
      submitting = true
      git_url = git_url.trim()

      if (https_mode && !git_url.startsWith("https://")) {
        error = new KilnError(
          "Please enter an HTTPS URL (starting with https://). SSH URLs are not supported in HTTPS mode.",
        )
        return
      }

      const result = await testAccess(git_url, pat_token)

      if (result.success && result.auth_method) {
        on_success(git_url, result.auth_method)
      } else if (is_ssh_url(git_url) && !result.success) {
        ssh_fail_dialog.show()
      } else if (result.auth_required) {
        on_auth_required(git_url)
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

<FormContainer
  submit_label="Check Access"
  on:submit={check_access}
  bind:submitting
  bind:error
  bind:saved
  focus_on_mount={true}
>
  {#if https_mode}
    <FormElement
      label="Repository URL"
      description="HTTPS URL of the git repository containing your Kiln project"
      info_description="Enter the HTTPS clone URL for your repository."
      id="git_url"
      inputType="input"
      bind:value={git_url}
      placeholder="https://github.com/your-org/your-repo.git"
    />
  {:else}
    <FormElement
      label="Repository URL"
      description="URL of the git repository containing your Kiln project"
      info_description="Enter the clone URL for your repository. Supports HTTPS URLs and SSH URLs (e.g. git@github.com:org/repo.git) if you have SSH keys configured."
      id="git_url"
      inputType="input"
      bind:value={git_url}
      placeholder="https://github.com/your-org/your-repo.git"
    />
  {/if}
</FormContainer>

<Dialog
  bind:this={ssh_fail_dialog}
  title="SSH Git Connection Failed"
  action_buttons={[
    {
      label: "Use HTTPS (Recommended)",
      isPrimary: true,
      action: switch_to_https,
    },
  ]}
>
  <p class="text-sm">
    An HTTPS connection is easier to set up (UI-based connection). We suggest
    using HTTPS unless you're a developer.
  </p>
</Dialog>
