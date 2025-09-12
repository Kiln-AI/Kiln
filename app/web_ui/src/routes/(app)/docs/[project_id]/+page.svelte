<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { page } from "$app/stores"

  let project_id = $page.params.project_id

  let sections = [
    {
      name: "Document Library",
      description: "Add or Browse Documents",
      button_text: "View Library",
      href: `/docs/library/${project_id}`,
      img: "/images/doc_library.svg",
    },
    {
      name: "Search Tools (RAG)",
      description: "Enable tasks to search your documents for knowledge.",
      button_text: "Manage Search Tools",
      href: `/docs/rag_configs/${project_id}`,
      img: "/images/card-search.svg",
    },
  ]
</script>

<AppPage
  title="Documents"
  subtitle="Add knowledge to your project with documents"
  limit_max_width
  action_buttons={[
    {
      label: "Manage Extractors",
      href: `/docs/extractors/${project_id}`,
      primary: false,
    },
  ]}
>
  <div class="flex flex-col gap-4">
    {#each sections as section}
      <a
        href={section.href}
        class="group flex items-center p-6 bg-white border border-gray-200 rounded-lg shadow-sm hover:shadow-md hover:border-gray-300 transition-all duration-200 max-w-[600px]"
      >
        <div class="flex-1 min-w-0">
          <h3 class="text-lg font-semibold mb-2">
            {section.name}
          </h3>
          <p class="text-gray-500 mb-4 text-sm leading-relaxed">
            {section.description}
          </p>
          <div
            class="btn btn-sm btn-primary btn-outline group-hover:bg-primary group-hover:text-primary-content group-hover:border-primary"
          >
            {section.button_text}
          </div>
        </div>

        <div
          class="flex-shrink-0 ml-6 w-36 h-36 flex items-center justify-center rounded-lg"
        >
          <img src={section.img} alt={section.name} class="w-24 h-24" />
        </div>
      </a>
    {/each}
  </div>
</AppPage>
