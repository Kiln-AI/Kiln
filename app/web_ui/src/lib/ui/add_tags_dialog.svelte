<script lang="ts">
  import Dialog from "./dialog.svelte"
  import TagPicker from "./tag_picker.svelte"

  export let title: string
  export let project_id: string | null = null
  export let task_id: string | null = null
  export let tag_type: "doc" | "task_run" = "task_run"
  export let add_tags: string[] = []
  export let onTagsChanged: (tags: string[]) => void = () => {}
  export let onAddTags: () => Promise<boolean> = async () => true

  let dialog: Dialog | null = null

  export function show() {
    dialog?.show()
  }

  export function close() {
    dialog?.close()
  }
</script>

<Dialog
  bind:this={dialog}
  {title}
  action_buttons={[
    { label: "Cancel", isCancel: true },
    {
      label: "Add Tags",
      asyncAction: onAddTags,
      disabled: add_tags.length == 0,
      isPrimary: true,
    },
  ]}
>
  <div>
    <div class="text-sm font-light text-gray-500 mb-2">
      Tags can be used to organize your items.
    </div>
    <TagPicker
      tags={add_tags}
      {tag_type}
      {project_id}
      {task_id}
      initial_expanded={true}
      on:tags_changed={(event) => {
        onTagsChanged(event.detail.current)
      }}
    />
  </div>
</Dialog>
