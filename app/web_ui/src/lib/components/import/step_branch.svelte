<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Warning from "$lib/ui/warning.svelte"
  import { listBranches, cloneRepo, testWriteAccess } from "$lib/git_sync/api"
  import { onMount } from "svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  export let git_url: string
  export let pat_token: string | null
  export let oauth_token: string | null = null
  export let auth_mode: string
  export let on_selected: (
    branch: string,
    clone_path: string,
    needs_credentials: boolean,
  ) => void

  let branches: string[] = []
  let default_branch: string | null = null
  let selected_branch = ""
  let loading = true
  let error: KilnError | null = null
  let submitting = false
  let saved = false
  let status_message = ""
  let write_denied = false

  onMount(async () => {
    try {
      const result = await listBranches(
        git_url,
        pat_token,
        auth_mode,
        oauth_token,
      )
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

  $: branch_option_groups = (() => {
    const sorted = [...branches].sort((a, b) => {
      if (a === default_branch) return -1
      if (b === default_branch) return 1
      return a.localeCompare(b)
    })
    const options = sorted.map((branch) => ({
      label: branch,
      value: branch,
      badge: branch === default_branch ? "default" : undefined,
    }))
    return [{ options }] as OptionGroup[]
  })()

  // Exported for test access only
  export function choose_another_branch() {
    write_denied = false
    error = null
    submitting = false
    status_message = ""
  }

  // Exported for test access only
  export async function clone_and_test() {
    let clone_path = ""
    try {
      error = null
      write_denied = false
      submitting = true
      status_message = "Cloning repository..."

      const clone_result = await cloneRepo(
        git_url,
        selected_branch,
        pat_token,
        auth_mode,
        oauth_token,
      )

      if (!clone_result.success) {
        error = new KilnError(clone_result.message)
        return
      }
      clone_path = clone_result.clone_path

      status_message = "Testing write access..."
      const write_result = await testWriteAccess(
        clone_path,
        pat_token,
        auth_mode,
        oauth_token,
      )

      if (!write_result.success) {
        if (write_result.write_denied) {
          write_denied = true
          return
        }
        if (write_result.auth_required) {
          on_selected(selected_branch, clone_path, true)
          return
        }
        error = new KilnError(write_result.message)
        return
      }

      on_selected(selected_branch, clone_path, false)
    } catch (e) {
      const err = createKilnError(e)
      if (
        err.getMessage().includes("401") ||
        err.getMessage().includes("auth")
      ) {
        on_selected(selected_branch, clone_path, true)
        return
      }
      error = err
    } finally {
      submitting = false
      status_message = ""
    }
  }
</script>

{#if write_denied}
  <div class="flex flex-col items-center py-8 gap-4">
    <div
      class="w-12 h-12 rounded-full bg-error/10 flex items-center justify-center"
    >
      <svg
        class="w-6 h-6 text-error"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
    </div>

    <h2 class="text-xl font-medium">Write Access Required</h2>

    <p class="text-sm text-gray-500 text-center max-w-md">
      Kiln Git Sync needs read/write access, but your permissions on this branch
      are read-only. Ask your Git administrator for write access, or switch to a
      branch where you have write permissions.
    </p>

    <div class="mt-2">
      <button class="btn btn-primary" on:click={choose_another_branch}>
        Choose Another Branch
      </button>
    </div>
  </div>
{:else}
  <h2 class="text-xl font-medium mb-2">Select Branch</h2>
  <p class="text-sm text-gray-500 mb-6">
    Choose the branch Kiln will auto-sync with. This will clone the repository
    to a local directory managed by Kiln.
  </p>

  {#if loading}
    <div class="flex justify-center py-8">
      <span class="loading loading-spinner loading-md"></span>
    </div>
  {:else if branches.length === 0 && error}
    <Warning warning_message={error.getMessage()} warning_color="error" />
  {:else}
    <FormContainer
      submit_label="Clone & Continue"
      on:submit={clone_and_test}
      bind:submitting
      bind:error
      bind:saved
      focus_on_mount={false}
      submitting_status={status_message}
    >
      <FormElement
        label="Branch"
        id="branch"
        inputType="fancy_select"
        info_description="This is the Git branch Kiln will auto-sync with."
        bind:value={selected_branch}
        fancy_select_options={branch_option_groups}
      />
    </FormContainer>
  {/if}
{/if}
