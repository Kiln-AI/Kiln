<script lang="ts">
  import StepUrl from "./step_url.svelte"
  import StepCredentials from "./step_credentials.svelte"
  import StepBranch from "./step_branch.svelte"
  import StepProject from "./step_project.svelte"
  import StepComplete from "./step_complete.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import { load_projects } from "$lib/stores"
  import { replaceState } from "$app/navigation"
  import { tick, onMount, onDestroy } from "svelte"
  import posthog from "posthog-js"
  import { isGitHubUrl, isGitLabUrl } from "$lib/git_sync/api"
  import {
    sync_url_query_param,
    read_url_query_param,
  } from "$lib/git_sync/url_utils"
  import {
    git_import_wizard_store,
    clear_wizard_store,
    validate_step_requirements,
    type WizardStep,
  } from "$lib/stores/git_import_wizard_store"

  export let create_link: string
  export let on_complete: (project_id: string) => void
  export let import_mode: "method" | "local" | "git" = "method"

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

  $: import_mode =
    current_step === "method"
      ? "method"
      : current_step === "local_file"
        ? "local"
        : "git"

  $: git_url = $git_import_wizard_store.git_url
  $: pat_token = $git_import_wizard_store.pat_token
  $: oauth_token = $git_import_wizard_store.oauth_token
  $: auth_mode = $git_import_wizard_store.auth_mode
  $: clone_path = $git_import_wizard_store.clone_path
  $: selected_branch = $git_import_wizard_store.selected_branch
  $: selected_project_path = $git_import_wizard_store.selected_project_path
  $: selected_project_id = $git_import_wizard_store.selected_project_id
  $: selected_project_name = $git_import_wizard_store.selected_project_name

  function update_store(fields: Partial<typeof $git_import_wizard_store>) {
    git_import_wizard_store.update((s) => ({ ...s, ...fields }))
  }

  const progress_steps: WizardStep[] = [
    "url",
    "credentials",
    "branch",
    "project",
  ]

  const step_progress_index: Partial<Record<WizardStep, number>> = {
    url: 0,
    credentials: 1,
    branch: 2,
    project: 3,
    complete: 3,
  }

  $: progress_index = step_progress_index[current_step] ?? -1

  $: show_progress =
    current_step !== "method" &&
    current_step !== "local_file" &&
    current_step !== "complete"

  function step_from_hash(): WizardStep {
    const hash = typeof window !== "undefined" ? window.location.hash : ""
    return hash_to_step[hash] || "method"
  }

  function redirect_if_missing_state(step: WizardStep): boolean {
    if (!validate_step_requirements(step)) {
      clear_wizard_store()
      replaceState(window.location.pathname + window.location.search, {})
      current_step = "method"
      return true
    }
    return false
  }

  function set_step(step: WizardStep) {
    if (step === "local_file") {
      import_project_path = ""
      import_error = null
      select_file_unavailable = false
      import_done = false
    }
    if (step === "method") {
      clear_wizard_store()
    } else {
      stale_clone_message = null
    }
    if (step !== "url") {
      sync_url_query_param("url", null)
    }
    current_step = step
    const hash = step_to_hash[step]
    if (hash) {
      window.location.hash = hash
    } else {
      replaceState(window.location.pathname + window.location.search, {})
    }
  }

  function on_hash_change() {
    const step = step_from_hash()
    if (redirect_if_missing_state(step)) return
    current_step = step
  }

  onMount(() => {
    const url_param = read_url_query_param("url")
    if (url_param) {
      update_store({ git_url: url_param })
      if (window.location.hash !== "#git") {
        window.location.hash = "#git"
      }
    }
    const step = step_from_hash()
    if (redirect_if_missing_state(step)) return
    current_step = step
    window.addEventListener("hashchange", on_hash_change)
  })

  onDestroy(() => {
    window.removeEventListener("hashchange", on_hash_change)
  })

  function go_to_credentials() {
    set_step("credentials")
  }

  function on_url_success(url: string, detected_auth_method: string) {
    update_store({ git_url: url, auth_mode: detected_auth_method })
    set_step("branch")
  }

  function on_url_auth_required(url: string) {
    update_store({ git_url: url })
    go_to_credentials()
  }

  function on_credentials_success(token: string, detected_auth_method: string) {
    if (detected_auth_method === "github_oauth") {
      update_store({
        oauth_token: token,
        pat_token: null,
        auth_mode: detected_auth_method,
      })
    } else {
      update_store({
        oauth_token: null,
        pat_token: token,
        auth_mode: detected_auth_method,
      })
    }
    set_step("branch")
  }

  function on_branch_selected(
    branch: string,
    path: string,
    needs_credentials: boolean,
  ) {
    update_store({ selected_branch: branch, clone_path: path })
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
    update_store({
      selected_project_path: project_path,
      selected_project_id: project_id,
      selected_project_name: project_name,
    })
    set_step("complete")
  }

  function git_host_label(url: string): string {
    if (isGitHubUrl(url)) return "github"
    if (isGitLabUrl(url)) return "gitlab"
    return "other"
  }

  function on_wizard_complete(project_id: string) {
    posthog.capture("import_project", {
      method: "git_sync",
      git_host: git_host_label(git_url ?? ""),
      auth_mode: auth_mode,
    })
    clear_wizard_store()
    on_complete(project_id)
  }

  function on_wizard_back() {
    set_step("method")
  }

  let stale_clone_message: string | null = null

  function on_stale_clone() {
    clear_wizard_store()
    stale_clone_message =
      "The cloned repository is no longer available (it may have been removed after a restart). Please start the import again."
    replaceState(window.location.pathname + window.location.search, {})
    current_step = "method"
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

      posthog.capture("import_project", { method: "local" })

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
          class="h-1 flex-1 rounded-full {i <= progress_index
            ? 'bg-primary'
            : 'bg-base-200'}"
        ></div>
      {/each}
    </div>
  {/if}

  {#if stale_clone_message && current_step === "method"}
    <div class="mb-4">
      <Warning warning_message={stale_clone_message} warning_color="warning" />
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
        on:click={() => {
          posthog.capture("git_sync_setup_start")
          set_step("url")
        }}
      >
        <div class="font-medium flex flex-row gap-2 items-center">
          <div class="flex-1">Git Auto Sync</div>
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
    <StepProject
      {clone_path}
      on_selected={on_project_selected}
      {on_stale_clone}
    />
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
      on_complete={on_wizard_complete}
      on_back={on_wizard_back}
      {on_stale_clone}
    />
  {/if}
</div>
