<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import StepUrl from "./step_url.svelte"
  import StepCredentials from "./step_credentials.svelte"
  import StepBranch from "./step_branch.svelte"
  import StepProject from "./step_project.svelte"
  import StepComplete from "./step_complete.svelte"

  type WizardStep = "url" | "credentials" | "branch" | "project" | "complete"

  let current_step: WizardStep = "url"
  let git_url = ""
  let pat_token: string | null = null
  let clone_path = ""
  let selected_branch = ""
  let selected_project_path = ""
  let selected_project_id = ""
  let selected_project_name = ""

  const step_order: WizardStep[] = [
    "url",
    "credentials",
    "branch",
    "project",
    "complete",
  ]

  $: step_index = step_order.indexOf(current_step)

  function go_to_credentials() {
    current_step = "credentials"
  }

  function on_url_success(url: string) {
    git_url = url
    current_step = "branch"
  }

  function on_url_auth_required(url: string) {
    git_url = url
    go_to_credentials()
  }

  function on_credentials_success(token: string) {
    pat_token = token
    current_step = "branch"
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
      current_step = "project"
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
    current_step = "complete"
  }

  function go_back() {
    const idx = step_order.indexOf(current_step)
    if (idx > 0) {
      current_step = step_order[idx - 1]
    }
  }
</script>

<AppPage
  title="Sync from Git"
  subtitle="Set up automatic git synchronization for a Kiln project"
  breadcrumbs={[
    { label: "Settings", href: "/settings" },
    { label: "Manage Projects", href: "/settings/manage_projects" },
  ]}
>
  <div class="max-w-[600px]">
    <div class="flex flex-row gap-2 mb-8">
      {#each step_order as _, i}
        <div
          class="h-1 flex-1 rounded-full {i <= step_index
            ? 'bg-primary'
            : 'bg-base-200'}"
        ></div>
      {/each}
    </div>

    {#if current_step === "url"}
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
        on_back={go_back}
      />
    {:else if current_step === "branch"}
      <StepBranch
        {git_url}
        {pat_token}
        on_selected={on_branch_selected}
        on_back={go_back}
      />
    {:else if current_step === "project"}
      <StepProject
        {clone_path}
        on_selected={on_project_selected}
        on_back={go_back}
      />
    {:else if current_step === "complete"}
      <StepComplete
        {git_url}
        {pat_token}
        {clone_path}
        branch={selected_branch}
        project_path={selected_project_path}
        project_id={selected_project_id}
        project_name={selected_project_name}
      />
    {/if}
  </div>
</AppPage>
