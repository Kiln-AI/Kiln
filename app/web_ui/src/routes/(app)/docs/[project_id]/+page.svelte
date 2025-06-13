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
    <a href={`/docs/library/${project_id}`} class="link">Documents (List)</a>
    <a href={`/docs/extractors/${project_id}`} class="link"
      >Document Extractors (List)</a
    >
  </div>
</AppPage>
