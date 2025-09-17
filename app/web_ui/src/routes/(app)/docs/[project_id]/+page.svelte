<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { page } from "$app/stores"
  import MultiIntro from "$lib/ui/multi_intro.svelte"

  $: project_id = $page.params.project_id
</script>

<AppPage
  title="Documents & Search"
  subtitle="Add searchable knowledge to your tasks"
  limit_max_width
>
  <MultiIntro
    intros={[
      {
        title: "Document Library",
        description:
          "Add or browse documents. Docs can be queried by Search Tools.",
        action_buttons: [
          {
            label: "View Library",
            href: `/docs/library/${project_id}`,
            primary: true,
          },
        ],
      },
      {
        title: "Search Tools (RAG)",
        description: "Enable tasks to search documents for knowledge.",
        action_buttons: [
          {
            label: "Manage Search Tools",
            href: `/docs/rag_configs/${project_id}`,
            primary: true,
          },
        ],
      },
    ]}
  >
    <div slot="image-0">
      <img src="/images/doc_library.svg" alt="Library" class="w-12 h-12" />
    </div>
    <div slot="image-1">
      <img src="/images/card-search.svg" alt="Search Tool" class="w-12 h-12" />
    </div>
  </MultiIntro>
</AppPage>
