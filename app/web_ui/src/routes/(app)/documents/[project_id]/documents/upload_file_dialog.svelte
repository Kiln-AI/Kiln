<script lang="ts">
  import { client } from "$lib/api_client"
  import { page } from "$app/stores"
  import Dialog from "$lib/ui/dialog.svelte"

  export let onUploadCompleted: () => void

  let selected_file: File | null = null
  let name: string = ""
  let description: string | null = null

  $: project_id = $page.params.project_id

  function handleFileSelect(event: Event) {
    const input = event.target as HTMLInputElement
    if (input.files && input.files[0]) {
      selected_file = input.files[0]

      if (name === "") {
        name = selected_file.name
      }
    }
  }

  async function handleUpload(): Promise<boolean> {
    if (!selected_file) {
      return false
    }

    const formData = new FormData()
    formData.append("file", selected_file)
    formData.append("name", name || selected_file.name)
    if (description) {
      formData.append("description", description)
    }

    const { error } = await client.POST(
      "/api/projects/{project_id}/documents",
      {
        params: {
          path: { project_id },
        },
        // todo: a transform must be set up to determine how to serialize multipart file uploads
        // see: https://github.com/openapi-ts/openapi-typescript/issues/1214
        body: formData as unknown as {
          file: string
          name: string
          description: string
        },
      },
    )

    if (error) {
      throw error
    }

    selected_file = null

    onUploadCompleted()

    return true
  }

  let dialog: Dialog | null = null

  export function show() {
    dialog?.show()
    selected_file = null
  }

  export function close() {
    dialog?.close()
    selected_file = null
    return true
  }

  function handleCancel() {
    close()
    return true
  }
</script>

<Dialog
  bind:this={dialog}
  title="Upload File"
  action_buttons={[
    { label: "Cancel", isCancel: true, action: () => handleCancel() },
    {
      label: "Upload",
      asyncAction: () => handleUpload(),
      disabled: !selected_file,
      isPrimary: true,
    },
  ]}
>
  <div class="font-light text-sm">
    <div class="space-y-2">
      <div>
        <p>
          Upload a file to your project's document store. The following file
          types are supported: [.pdf]
        </p>
      </div>
    </div>
    <form class="grid grid-cols-1 gap-2 mt-4">
      <div class="mt-4 grid grid-cols-1 gap-2">
        <div>
          <label for="name" class="label font-medium p-0 text-sm"
            >Name (optional)</label
          >
          <p class="text-xs text-gray-500">
            The name is for your reference. It does not impact the file's
            processing.
          </p>
        </div>
        <input
          type="text"
          id="name"
          class="input input-bordered py-2 w-full"
          bind:value={name}
          autocomplete="off"
        />
      </div>
      <div class="mt-4 grid grid-cols-1 gap-2">
        <div>
          <label for="description" class="label font-medium p-0 text-sm"
            >Description (optional)</label
          >
          <p class="text-xs text-gray-500">
            The description is for your reference. It does not impact the file's
            processing.
          </p>
        </div>
        <textarea
          id="description"
          class="input input-bordered py-2 w-full h-[100px]"
          bind:value={description}
        />
      </div>
      <div class="mt-4 grid grid-cols-1 gap-2">
        <input
          type="file"
          class="file-input file-input-bordered w-full"
          on:change={handleFileSelect}
          accept=".pdf"
        />
      </div>
    </form>
  </div>
</Dialog>
