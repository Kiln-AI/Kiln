<script lang="ts">
  // Generic no-op stub for the RAG form's heavy child components (the five
  // create-sub-config dialogs, TagSelector, TemplatePropertyOverview). It
  // exports the props the parent binds to (`dialog`, `selected_tags`) so the
  // parent's `bind:` directives resolve, and renders nothing.
  export let dialog: unknown = null
  export let selected_tags: string[] = []
  export let keyboard_submit = false
  export let project_id = ""
  export let template: unknown = null
</script>
