<script lang="ts">
  import Intro from "$lib/ui/intro.svelte"

  export let project_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <Intro
    title="Create a Search Tool"
    description_paragraphs={[]}
    action_buttons={[
      {
        label: "Create Search Tool",
        href: `/docs/rag_configs/${project_id}/create_rag_config`,
        is_primary: true,
      },
    ]}
  >
    <div slot="description">
      Allow your tasks to search the knowledge in your documents
      (Retrieval-Augmented Generation).
    </div>
    <div slot="icon">
      <img src="/images/card-search.svg" alt="Search Tool" class="w-10 h-10" />
    </div>
  </Intro>
</div>
