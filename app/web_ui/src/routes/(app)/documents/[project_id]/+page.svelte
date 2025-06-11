<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { page } from "$app/stores"

  let project_id = $page.params.project_id
</script>

<AppPage
  title="Documents"
  sub_subtitle="Read the Docs"
  sub_subtitle_link="#"
  action_buttons={[]}
>
  <div class="mt-4 grid grid-cols-1 gap-2">
    <a href={`/documents/${project_id}/documents`} class="link"
      >Documents (List)</a
    >
    <a href={`/documents/${project_id}/extractors`} class="link"
      >Document Extractors (List)</a
    >
  </div>
</AppPage>
