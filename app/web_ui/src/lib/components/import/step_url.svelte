<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { testAccess } from "$lib/git_sync/api"
  import { try_convert_ssh_to_https } from "$lib/git_sync/url_utils"

  export let initial_url: string = ""
  export let pat_token: string | null = null
  export let on_success: (url: string) => void
  export let on_auth_required: (url: string) => void

  let git_url = initial_url
  let error: KilnError | null = null
  let submitting = false
  let saved = false

  function normalize_url() {
    git_url = try_convert_ssh_to_https(git_url)
  }

  async function check_access() {
    try {
      error = null
      submitting = true
      normalize_url()

      const result = await testAccess(git_url, pat_token)

      if (result.success) {
        on_success(git_url)
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
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div on:focusout={normalize_url}>
    <FormElement
      label="Repository URL"
      description="HTTPS URL of the git repository containing your Kiln project"
      info_description="Enter the HTTPS clone URL for your repository. SSH URLs are not supported."
      id="git_url"
      inputType="input"
      bind:value={git_url}
      placeholder="https://github.com/your-org/your-repo.git"
    />
  </div>
</FormContainer>
