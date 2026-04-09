<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Warning from "$lib/ui/warning.svelte"
  import { testAccess } from "$lib/git_sync/api"

  export let initial_url: string = ""
  export let pat_token: string | null = null
  export let on_success: (url: string) => void
  export let on_auth_required: (url: string) => void

  let git_url = initial_url
  let error: KilnError | null = null
  let submitting = false
  let saved = false

  async function check_access() {
    try {
      error = null
      submitting = true
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

<h2 class="text-xl font-medium mb-2">Repository URL</h2>
<p class="text-sm text-gray-500 mb-6">
  Enter the HTTPS URL of the git repository containing your Kiln project.
</p>

<FormContainer
  submit_label="Check Access"
  on:submit={check_access}
  bind:submitting
  bind:error
  bind:saved
  focus_on_mount={true}
>
  <FormElement
    label="Git URL"
    id="git_url"
    inputType="input"
    bind:value={git_url}
    placeholder="https://github.com/your-org/your-repo.git"
  />

  <Warning
    warning_message="Enter the HTTPS clone URL for your repository. SSH URLs are not supported in the setup wizard."
    warning_color="gray"
    warning_icon="info"
  />
</FormContainer>
