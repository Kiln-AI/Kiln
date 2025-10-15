<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import DataGenIntro from "./data_gen_intro.svelte"
  import { indexedDBStore } from "$lib/stores/index_db_store"
  import { writable, type Writable } from "svelte/store"

  let loading = true
  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  // we only need gen_type to do the routing, the type-specific data is handled by the
  // mode-specific pages we redirect to
  type SavedDataGenState = {
    gen_type?: "training" | "eval" | null
  }

  let saved_state: Writable<SavedDataGenState> = writable({
    gen_type: null,
  })

  onMount(async () => {
    await handle_routing()
  })

  async function handle_routing() {
    loading = true
    const reason_param = $page.url.searchParams.get("reason")

    // Eval/Fine-tuning modes redirect to synth page - this is when we explicitly link back
    // to the synth page (e.g. via toast UI)
    if (reason_param === "eval" || reason_param === "fine_tune") {
      const params = new URLSearchParams($page.url.searchParams)
      await goto(
        `/generate/${project_id}/${task_id}/synth?${params.toString()}`,
      )
      return
    }

    // user lands on this page without any specific state in the URL, we want to redirect
    // them to wherever they last were (i.e. synth page) if they have any ongoing session
    try {
      const currentSessionGenType = await getCurrentSessionGenType()
      switch (currentSessionGenType) {
        case "training":
          await goto(`/generate/${project_id}/${task_id}/synth`)
          return
        case "eval":
          await goto(`/generate/${project_id}/${task_id}/synth`)
          return
        case null:
          // no ongoing session, stay on this page and show intro
          break
        default: {
          // invalid gen type - typecheck will flag if upstream typing adds a new case
          const value: never = currentSessionGenType
          console.error(`Invalid gen type: ${value}`)
          break
        }
      }
    } catch (error) {
      console.error("Error checking for ongoing session:", error)
    }

    loading = false
  }

  async function getCurrentSessionGenType(): Promise<
    "training" | "eval" | null
  > {
    const synth_data_key = `synth_data_${project_id}_${task_id}_v2`
    const { store, initialized } = indexedDBStore(synth_data_key, {
      gen_type: null,
      template_id: null,
      eval_id: null,
      splits: {},
      root_node: { topic: "", samples: [], sub_topics: [] },
    })
    // Wait for the store to be initialized, then set the state
    await initialized
    saved_state = store
    return $saved_state.gen_type || null
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Synthetic Data Generation"
    no_y_padding
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/synthetic-data-generation"
    action_buttons={[
      {
        label: "Docs & Guide",
        href: "https://docs.kiln.tech/docs/synthetic-data-generation",
      },
    ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else}
      <DataGenIntro
        generate_subtopics={() => {}}
        generate_samples={() => {}}
        {project_id}
        {task_id}
        is_setup={false}
      />
    {/if}
  </AppPage>
</div>
