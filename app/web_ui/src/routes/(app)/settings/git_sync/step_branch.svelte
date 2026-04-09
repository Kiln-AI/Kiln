<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Warning from "$lib/ui/warning.svelte"
  import { listBranches, cloneRepo, testWriteAccess } from "$lib/git_sync/api"
  import { onMount } from "svelte"

  export let git_url: string
  export let pat_token: string | null
  export let on_selected: (
    branch: string,
    clone_path: string,
    needs_credentials: boolean,
  ) => void
  export let on_back: () => void

  let branches: string[] = []
  let default_branch: string | null = null
  let selected_branch = ""
  let loading = true
  let error: KilnError | null = null
  let submitting = false
  let saved = false
  let status_message = ""

  onMount(async () => {
    try {
      const result = await listBranches(git_url, pat_token)
      branches = result.branches
      default_branch = result.default_branch

      if (default_branch && branches.includes(default_branch)) {
        selected_branch = default_branch
      } else if (branches.length > 0) {
        selected_branch = branches[0]
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  })

  $: branch_options = branches.map((b): [string, string] => [
    b,
    b === default_branch ? `${b} (default)` : b,
  ])

  async function clone_and_test() {
    try {
      error = null
      submitting = true
      status_message = "Cloning repository..."

      const clone_result = await cloneRepo(git_url, selected_branch, pat_token)

      if (!clone_result.success) {
        error = new KilnError(clone_result.message)
        return
      }

      status_message = "Testing write access..."
      const write_result = await testWriteAccess(
        clone_result.clone_path,
        pat_token,
      )

      if (!write_result.success) {
        if (write_result.auth_required) {
          on_selected(selected_branch, clone_result.clone_path, true)
          return
        }
        error = new KilnError(write_result.message)
        return
      }

      on_selected(selected_branch, clone_result.clone_path, false)
    } catch (e) {
      const err = createKilnError(e)
      if (
        err.getMessage().includes("401") ||
        err.getMessage().includes("auth")
      ) {
        on_selected(selected_branch, "", true)
        return
      }
      error = err
    } finally {
      submitting = false
      status_message = ""
    }
  }
</script>

<h2 class="text-xl font-medium mb-2">Select Branch</h2>
<p class="text-sm text-gray-500 mb-6">
  Choose the branch to sync with. This will clone the repository to a local
  directory managed by Kiln.
</p>

{#if loading}
  <div class="flex justify-center py-8">
    <span class="loading loading-spinner loading-md"></span>
  </div>
{:else if branches.length === 0 && error}
  <Warning warning_message={error.getMessage()} warning_color="error" />
  <div class="mt-4">
    <button class="btn btn-ghost btn-sm" on:click={on_back}>Back</button>
  </div>
{:else}
  <FormContainer
    submit_label="Clone & Continue"
    on:submit={clone_and_test}
    bind:submitting
    bind:error
    bind:saved
    focus_on_mount={false}
  >
    <FormElement
      label="Branch"
      id="branch"
      inputType="select"
      bind:value={selected_branch}
      select_options={branch_options}
    />

    {#if status_message}
      <div class="text-sm text-gray-500 flex items-center gap-2">
        <span class="loading loading-spinner loading-sm"></span>
        {status_message}
      </div>
    {/if}
  </FormContainer>

  <div class="mt-4">
    <button class="btn btn-ghost btn-sm" on:click={on_back}>Back</button>
  </div>
{/if}
