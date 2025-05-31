<script lang="ts">
  import { _ } from "svelte-i18n"
  import AppPage from "../../app_page.svelte"
  import EditProject from "../../../(fullscreen)/setup/(setup)/create_project/edit_project.svelte"
</script>

<div class="max-w-[600px]">
  <AppPage
    title={$_("project.add_project")}
    subtitle={$_("project.add_project_subtitle")}
  >
    <EditProject redirect_on_created="/settings/create_task" />
  </AppPage>
</div>
