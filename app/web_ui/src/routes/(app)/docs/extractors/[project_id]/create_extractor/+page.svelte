<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { ui_state } from "$lib/stores"
  import AppPage from "../../../../app_page.svelte"
  import CreateExtractorForm from "./create_extractor_form.svelte"
</script>

<AppPage
  title="Create Document Extractor"
  subtitle="A configuration for extracting data from your documents."
  breadcrumbs={$ui_state.current_task_id
    ? [
        {
          label: "Optimize",
          href: `/optimize/${$page.params.project_id}/${$ui_state.current_task_id}`,
        },
        {
          label: "Docs & Search",
          href: `/docs/${$page.params.project_id}`,
        },
        {
          label: "Extractors",
          href: `/docs/extractors/${$page.params.project_id}`,
        },
      ]
    : [
        {
          label: "Docs & Search",
          href: `/docs/${$page.params.project_id}`,
        },
        {
          label: "Extractors",
          href: `/docs/extractors/${$page.params.project_id}`,
        },
      ]}
>
  <div class="max-w-[900px]">
    <CreateExtractorForm
      on:success={() => {
        goto(`/docs/extractors/${$page.params.project_id}`)
      }}
    />
  </div>
</AppPage>
