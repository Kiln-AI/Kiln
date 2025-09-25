<script lang="ts">
  import { page } from "$app/stores"
  import AppPage from "../../../../app_page.svelte"
  import { goto } from "$app/navigation"
  import { rag_config_templates } from "../add_search_tool/rag_config_templates"
  import EditRagConfigForm from "./edit_rag_config_form.svelte"

  $: project_id = $page.params.project_id
  const template_id = $page.url.searchParams.get("template_id")
  const template = template_id ? rag_config_templates[template_id] : null

  let loading: boolean = false
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Create Search Tool (RAG)"
    subtitle="Define parameters for how this tool will search and retrieve your documents"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/documents-and-search-rag#building-a-search-tool"
    breadcrumbs={[
      {
        label: "Docs & Search",
        href: `/docs/${project_id}`,
      },
      {
        label: "Search Tools",
        href: `/docs/rag_configs/${project_id}`,
      },
      {
        label: "Add Search Tool",
        href: `/docs/rag_configs/${project_id}/add_search_tool`,
      },
    ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else}
      <EditRagConfigForm
        {template}
        on:success={() => {
          goto(`/docs/rag_configs/${project_id}`)
        }}
      />
    {/if}
  </AppPage>
</div>
