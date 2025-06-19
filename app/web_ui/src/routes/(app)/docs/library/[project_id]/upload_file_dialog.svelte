<script lang="ts">
  import { client } from "$lib/api_client"
  import { page } from "$app/stores"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"

  export let onUploadCompleted: () => void

  let selected_file: File | null = null
  let name: string = ""
  let description: string | null = null
  const supported_file_types = [
    ".pdf",
    ".csv",
    ".txt",
    ".md",
    ".html",
    ".jpg",
    ".jpeg",
    ".png",
    ".mp4",
    ".mov",
    ".mp3",
    ".wav",
    ".ogg",
  ]

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

  let upload_in_progress: boolean = false
  async function handleUpload(): Promise<boolean> {
    upload_in_progress = true
    try {
      const success = await uploadFile()
      return success
    } finally {
      upload_in_progress = false
    }
  }

  async function uploadFile(): Promise<boolean> {
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
    name = ""
    description = null

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

  function file_supported(file: File): boolean {
    if (!file) {
      return false
    }
    return supported_file_types.includes(
      ("." + (file.name.split(".").pop() || "")).toLowerCase(),
    )
  }
</script>

<Dialog
  bind:this={dialog}
  title={upload_in_progress ? "Processing Document" : "Add Document"}
  action_buttons={[
    { label: "Cancel", isCancel: true, action: () => handleCancel() },
    {
      label: "Upload",
      asyncAction: () => handleUpload(),
      disabled: !selected_file || !file_supported(selected_file),
      isPrimary: true,
    },
  ]}
>
  <div class="font-light text-sm">
    <div class="space-y-2">
      <div>
        <p>
          Add a file to your project's document store. The following file types
          are supported:
        </p>
        <ul class="list-disc list-inside mt-2">
          <li>Documents: .pdf, .csv, .txt, .md, .html</li>
          <li>Images: .jpg, .jpeg, .png</li>
          <li>Videos: .mp4, .mov</li>
          <li>Audio: .mp3, .wav, .ogg</li>
        </ul>
      </div>
    </div>
    <form class="flex flex-col gap-4 mt-8">
      <input
        type="file"
        class="file-input file-input-bordered w-full"
        on:change={handleFileSelect}
        accept={supported_file_types.join(",")}
      />
      {#if selected_file && !file_supported(selected_file)}
        <Warning
          warning_message={`Select file isn't supported. Please upload a file with one of the following extensions: ${supported_file_types.join(", ")}`}
        />
      {/if}
      <FormElement
        label="Name"
        optional={true}
        description="A name for your reference."
        bind:value={name}
        id="name"
        inputType="input"
      />
      <FormElement
        label="Description"
        optional={true}
        description="A description for your reference."
        bind:value={description}
        id="description"
        inputType="textarea"
      />
    </form>
  </div>
</Dialog>
