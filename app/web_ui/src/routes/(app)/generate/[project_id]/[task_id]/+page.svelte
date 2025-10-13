<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import DataGenIntro from "./data_gen_intro.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  onMount(() => {
    handle_routing()
  })

  function handle_routing() {
    const reason_param = $page.url.searchParams.get("reason")

    // Eval/Fine-tuning modes redirect to synth page
    if (reason_param === "eval" || reason_param === "fine_tune") {
      const params = new URLSearchParams($page.url.searchParams)
      goto(`/generate/${project_id}/${task_id}/synth?${params.toString()}`)
      return
    }
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
    <DataGenIntro
      generate_subtopics={() => {}}
      generate_samples={() => {}}
      {project_id}
      {task_id}
      is_setup={false}
    />
  </AppPage>
</div>
