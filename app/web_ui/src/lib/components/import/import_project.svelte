<script lang="ts">
  import StepUrl from "./step_url.svelte"
  import StepCredentials from "./step_credentials.svelte"
  import StepBranch from "./step_branch.svelte"
  import StepProject from "./step_project.svelte"
  import StepComplete from "./step_complete.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import { load_projects } from "$lib/stores"
  import { tick, onMount, onDestroy } from "svelte"
  import posthog from "posthog-js"
  import {
    sync_url_query_param,
    read_url_query_param,
  } from "$lib/git_sync/url_utils"

  export let create_link: string
  export let on_complete: (project_id: string) => void

  type WizardStep =
    | "method"
    | "local_file"
    | "url"
    | "credentials"
    | "branch"
    | "project"
    | "complete"

  const hash_to_step: Record<string, WizardStep> = {
    "#local": "local_file",
    "#git": "url",
    "#git-credentials": "credentials",
    "#git-branch": "branch",
    "#git-project": "project",
    "#git-complete": "complete",
  }

  const step_to_hash: Partial<Record<WizardStep, string>> = {
    local_file: "#local",
    url: "#git",
    credentials: "#git-credentials",
    branch: "#git-branch",
    project: "#git-project",
    complete: "#git-complete",
  }

  let current_step: WizardStep = "method"
  let git_url = ""
  let pat_token: string | null = null
  let oauth_token: string | null = null
  let auth_mode: string = "system_keys"
  let clone_path = ""
  let selected_branch = ""
  let selected_project_path = ""
  let selected_project_id = ""
  let selected_project_name = ""

  // Progress bar steps — credentials is excluded because it's a side-quest
  // that can happen at multiple points (after URL or after branch)
  const progress_steps: WizardStep[] = ["url", "branch", "project", "complete"]

  // Map each step to its progress index (-1 if not a progress step)
  function progress_index_of(step: WizardStep): number {
    return progress_steps.indexOf(step)
  }

  let max_progress = 0

  $: {
    const idx = progress_index_of(current_step)
    if (idx > max_progress) {
      max_progress = idx
    }
  }

  $: show_progress =
    current_step !== "method" &&
    current_step !== "local_file" &&
    current_step !== "complete"

  function step_from_hash(): WizardStep {
    const hash = typeof window !== "undefined" ? window.location.hash : ""
    return hash_to_step[hash] || "method"
  }

  function set_step(step: WizardStep) {
    if (step === "local_file") {
      import_project_path = ""
      import_error = null
      select_file_unavailable = false
      import_done = false
    }
    if (step !== "url") {
      sync_url_query_param("url", null)
    }
    current_step = step
    const hash = step_to_hash[step]
    if (hash) {
      window.location.hash = hash
    } else {
      // "method" step — clear hash without pushing a new history entry
      history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search,
      )
    }
  }

  function on_hash_change() {
    current_step = step_from_hash()
  }

  onMount(() => {
    const url_param = read_url_query_param("url")
    if (url_param) {
      git_url = url_param
      // Use window.location.hash directly instead of set_step("url") because
      // set_step clears the "url" query param, which we just read above.
      if (window.location.hash !== "#git") {
        window.location.hash = "#git"
      }
    }
    current_step = step_from_hash()
    window.addEventListener("hashchange", on_hash_change)
  })

  onDestroy(() => {
    window.removeEventListener("hashchange", on_hash_change)
  })

  function go_to_credentials() {
    set_step("credentials")
  }

  function on_url_success(url: string, detected_auth_method: string) {
    git_url = url
    auth_mode = detected_auth_method
    set_step("branch")
  }

  function on_url_auth_required(url: string) {
    git_url = url
    go_to_credentials()
  }

  function on_credentials_success(token: string, detected_auth_method: string) {
    if (detected_auth_method === "github_oauth") {
      oauth_token = token
      pat_token = null
    } else {
      pat_token = token
      oauth_token = null
    }
    auth_mode = detected_auth_method
    set_step("branch")
  }

  function on_branch_selected(
    branch: string,
    path: string,
    needs_credentials: boolean,
  ) {
    selected_branch = branch
    clone_path = path
    if (needs_credentials) {
      go_to_credentials()
    } else {
      set_step("project")
    }
  }

  function on_project_selected(
    project_path: string,
    project_id: string,
    project_name: string,
  ) {
    selected_project_path = project_path
    selected_project_id = project_id
    selected_project_name = project_name
    set_step("complete")
  }

  // Local file import logic
  let select_file_unavailable = false
  $: show_select_file = !select_file_unavailable && !import_project_path
  $: import_submit_visible = !show_select_file
  let import_project_path = ""
  let import_error: KilnError | null = null
  let import_submitting = false
  let import_saved = false
  let import_done = false

  async function select_project_file() {
    try {
      const { data, error: get_error } = await client.GET(
        "/api/select_kiln_file",
        {
          params: {
            query: {
              title: "Select project.kiln File",
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      import_project_path = data.file_path ?? ""
    } catch (_) {
      import_error = new KilnError(
        "Can't open file selector. Please enter the path manually.",
      )
      select_file_unavailable = true
    }
  }

  const import_project = async () => {
    try {
      import_submitting = true
      import_saved = false
      const { data, error: post_error } = await client.POST(
        "/api/import_project",
        {
          params: {
            query: {
              project_path: import_project_path,
            },
          },
        },
      )
      if (post_error) {
        throw post_error
      }

      posthog.capture("import_project", {})

      await load_projects()
      import_done = true
      import_saved = true
      await tick()

      if (data?.id) {
        on_complete(data.id)
      }
    } catch (e) {
      import_error = createKilnError(e)
    } finally {
      import_submitting = false
    }
  }
</script>

<div class="max-w-[600px]">
  {#if show_progress}
    <div class="flex flex-row gap-2 mb-8">
      {#each progress_steps as _, i}
        <div
          class="h-1 flex-1 rounded-full {i <= max_progress
            ? 'bg-primary'
            : 'bg-base-200'}"
        ></div>
      {/each}
    </div>
  {/if}

  {#if current_step === "method"}
    <div class="flex flex-col gap-4">
      <button
        class="w-full text-left p-5 border rounded-lg hover:border-primary hover:bg-base-200 transition-colors"
        on:click={() => set_step("local_file")}
      >
        <div class="font-medium">Import from Local Folder</div>
        <div class="text-sm text-gray-500 mt-1">
          Select an existing project.kiln file from your computer.
        </div>
      </button>

      <button
        class="w-full text-left p-5 border rounded-lg hover:border-primary hover:bg-base-200 transition-colors"
        on:click={() => set_step("url")}
      >
        <div class="font-medium flex flex-row gap-2 items-center">
          <div class="flex-1">Automatic Git Sync</div>
          <div class="badge badge-secondary">Beta</div>
        </div>
        <div class="text-sm text-gray-500 mt-1">
          Requires a hosted git repository.
        </div>
      </button>
    </div>

    <p class="mt-6 text-center">
      Or
      <a class="link font-bold" href={create_link}>create a new project</a>
    </p>
  {:else if current_step === "local_file"}
    <p class="font-medium mb-6">
      Select or enter the path to a project.kiln file on your computer.
    </p>

    {#if !import_done}
      <FormContainer
        submit_label="Import Project"
        on:submit={import_project}
        bind:submitting={import_submitting}
        bind:error={import_error}
        bind:saved={import_saved}
        bind:submit_visible={import_submit_visible}
      >
        {#if show_select_file}
          <button class="btn btn-primary" on:click={select_project_file}>
            Select Project File
          </button>
        {:else}
          <FormElement
            label="Existing Project Path"
            description="The path to a project.kiln file. For example, /Users/username/my_project/project.kiln"
            info_description="You must enter the full path to the file, not just a filename. The path should be to a project.kiln file."
            id="import_project_path"
            inputType="input"
            bind:value={import_project_path}
          />
        {/if}
      </FormContainer>
    {/if}
  {:else if current_step === "url"}
    <StepUrl
      initial_url={git_url}
      {pat_token}
      on_success={on_url_success}
      on_auth_required={on_url_auth_required}
    />
  {:else if current_step === "credentials"}
    <StepCredentials
      {git_url}
      initial_token={pat_token}
      on_success={on_credentials_success}
    />
  {:else if current_step === "branch"}
    <StepBranch
      {git_url}
      {pat_token}
      {oauth_token}
      {auth_mode}
      on_selected={on_branch_selected}
    />
  {:else if current_step === "project"}
    <StepProject {clone_path} on_selected={on_project_selected} />
  {:else if current_step === "complete"}
    <StepComplete
      {git_url}
      {pat_token}
      {oauth_token}
      {auth_mode}
      {clone_path}
      branch={selected_branch}
      project_path={selected_project_path}
      project_id={selected_project_id}
      project_name={selected_project_name}
      {on_complete}
      on_back={() => set_step("method")}
    />
  {/if}
</div>
