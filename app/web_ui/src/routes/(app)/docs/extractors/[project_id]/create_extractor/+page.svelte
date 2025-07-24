<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import AppPage from "../../../../app_page.svelte"
  import CreateExtractorForm from "./create_extractor_form.svelte"
</script>

<AppPage
  title="Create Document Extractor"
  subtitle="A configuration for extracting data from your documents."
>
  <div class="max-w-[900px]">
    <CreateExtractorForm
      on:success={() => {
        goto(`/docs/extractors/${$page.params.project_id}`)
      }}
    />
  </div>
</AppPage>
