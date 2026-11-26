<script lang="ts">
  import { page } from "$app/stores"
  import AppPage from "../../../app_page.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import CodeTrustQuestion from "$lib/components/code_tools/code_trust_question.svelte"
  import { agentInfo } from "$lib/agent"
  import type { KilnError } from "$lib/utils/error_handlers"
  import {
    grant_code_trust,
    load_trust_code,
    type TrustCodeState,
  } from "./trust_code"

  agentInfo.set({
    name: "Trust Code",
    description:
      "Asks the user to grant code trust to a project for this app session, so new code tools and code evals can run. The user's own agent links to this page.",
  })

  $: project_id = $page.params.project_id!

  let state: TrustCodeState = { kind: "loading" }
  let granting = false
  let grant_error: KilnError | null = null

  $: load(project_id)

  async function load(id: string) {
    state = { kind: "loading" }
    grant_error = null
    const loaded = await load_trust_code(id)
    if (id === project_id) {
      state = loaded
    }
  }

  async function grant() {
    if (state.kind !== "question") {
      return
    }
    const project_name = state.project_name
    granting = true
    grant_error = await grant_code_trust(project_id)
    granting = false
    if (!grant_error) {
      state = { kind: "trusted", project_name }
    }
  }

  $: subtitle =
    state.kind === "question" || state.kind === "trusted"
      ? `Trust the code in Project "${state.project_name}"?`
      : ""
</script>

<AppPage
  title="Trust Code"
  {subtitle}
  breadcrumbs={[{ label: "Settings", href: "/settings" }]}
>
  {#if state.kind === "loading"}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if state.kind === "error"}
    <div class="max-w-lg">
      <Warning
        warning_color="error"
        warning_message={state.error.getMessage()}
      />
    </div>
  {:else if state.kind === "trusted"}
    <div class="max-w-lg" data-testid="trust-code-granted">
      <Warning
        warning_color="success"
        warning_icon="check"
        large_icon={true}
        warning_message="Return to your agent and tell it code trust was granted."
      />
    </div>
  {:else}
    <div class="max-w-lg flex flex-col gap-6">
      <CodeTrustQuestion />
      {#if grant_error}
        <Warning
          warning_color="error"
          warning_message={grant_error.getMessage()}
        />
      {/if}
      <div class="flex justify-end">
        <button
          class="btn btn-warning"
          disabled={granting}
          on:click={grant}
          data-testid="trust-code-grant"
        >
          {#if granting}
            <span class="loading loading-spinner loading-sm"></span>
          {/if}
          I Trust This Code
        </button>
      </div>
    </div>
  {/if}
</AppPage>
