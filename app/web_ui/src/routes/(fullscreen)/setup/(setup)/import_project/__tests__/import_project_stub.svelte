<script lang="ts" context="module">
  // Captures the on_complete callback the page passes to ImportProject, so a
  // test can finish an import without the real wizard.
  export const importProjectProps: {
    on_complete?: (project_id: string) => void
  } = {}
</script>

<script lang="ts">
  export let create_link: string
  export let on_complete: (project_id: string) => void
  importProjectProps.on_complete = on_complete
</script>

<div data-testid="import-project-stub" data-create-link={create_link}></div>
