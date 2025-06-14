<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { page } from "$app/stores"

  let project_id = $page.params.project_id

  let sections = [
    {
      name: "Document Library",
      description: "Manage, upload and browse documents.",
      button_text: "Browse Documents",
      href: `/docs/library/${project_id}`,
    },
    {
      name: "Document Extractors",
      description:
        "Create and manage document extractors. An extractor is a particular way of extracting information from your documents.",
      button_text: "Manage Extractors",
      href: `/docs/extractors/${project_id}`,
    },
  ]
</script>

<AppPage
  title="Documents"
  sub_subtitle="Read the Docs"
  sub_subtitle_link="#"
  action_buttons={[]}
>
  <div class="flex flex-col gap-8 max-w-[700px] mt-16">
    {#each sections as section}
      <div class="flex flex-col md:flex-row gap-4 md:items-center">
        <div class="grow">
          <h3 class="font-medium">{section.name}</h3>
          <p class="text-sm text-gray-500">{section.description}</p>
        </div>
        <a href={section.href} class="btn" style="min-width: 14rem">
          {section.button_text}
        </a>
      </div>
    {/each}
  </div>
</AppPage>
