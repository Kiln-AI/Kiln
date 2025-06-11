<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "../../../../../../lib/api_client"
  import type { ExtractorType, OutputFormat } from "../../../../../../lib/types"
  import { createKilnError } from "../../../../../../lib/utils/error_handlers"
  import FormElement from "../../../../../../lib/utils/form_element.svelte"
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "../../../../../../lib/utils/form_container.svelte"
  import { goto } from "$app/navigation"

  $: project_id = $page.params.project_id

  let extractor_options = [
    {
      label: "Gemini: Gemini 2.0 Flash",
      value: "gemini:::gemini-2.0-flash",
    },
  ]

  let loading: boolean = false
  let name: string | null = null
  let description: string = ""
  let selected_extractor_option: string = extractor_options[0].value
  let output_format: "text/markdown" | "text/plain" = "text/markdown"
  let prompt_document: string | null = null
  let prompt_image: string | null = null
  let prompt_video: string | null = null
  let prompt_audio: string | null = null

  $: extractor_type = selected_extractor_option.split(":::")[0]
  $: model_name = selected_extractor_option.split(":::")[1]

  async function create_extractor_config() {
    try {
      loading = true
      const { error: create_extractor_error } = await client.POST(
        "/api/projects/{project_id}/create_extractor_config",
        {
          params: {
            path: {
              project_id,
            },
          },
          body: {
            name: name || null,
            description: description || null,
            extractor_type: extractor_type as unknown as ExtractorType,
            output_format: output_format as unknown as OutputFormat,
            properties: {
              model_name,
              prompt_document: prompt_document || null,
              prompt_image: prompt_image || null,
              prompt_video: prompt_video || null,
              prompt_audio: prompt_audio || null,
            },
            passthrough_mimetypes: ["text/plain", "text/markdown"],
          },
        },
      )

      if (create_extractor_error) {
        throw createKilnError(create_extractor_error)
      }

      goto(`/documents/${project_id}/extractors`)
    } finally {
      loading = false
    }
  }
</script>

<AppPage
  title="Create Document Extractor"
  sub_subtitle="Create a new document extractor"
  sub_subtitle_link="#"
  no_y_padding
  action_buttons={[]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else}
    <div class="my-4">
      <FormContainer
        submit_visible={true}
        submit_label="Create Extractor"
        on:submit={create_extractor_config}
        bind:submitting={loading}
      >
        <div class="flex flex-col gap-2">
          <div class="form-control">
            <label class="label" for="extractor_type">Extractor Type</label>
            <select
              class="select select-bordered"
              bind:value={selected_extractor_option}
            >
              {#each extractor_options as option}
                <option
                  value={option.value}
                  selected={selected_extractor_option === option.value}
                >
                  {option.label}
                </option>
              {/each}
            </select>
          </div>
          <div class="form-control">
            <label class="label" for="output_format">Output Format</label>
            <select class="select select-bordered" bind:value={output_format}>
              <option value="text/markdown">Markdown</option>
              <option value="text/plain">Plain Text</option>
            </select>
          </div>
        </div>
        <div class="mt-4">
          <div class="collapse collapse-arrow bg-base-200">
            <input type="checkbox" class="peer" />
            <div class="collapse-title font-medium">Extractor Options</div>
            <div class="collapse-content flex flex-col gap-4">
              <FormElement
                label="Name"
                description="A name to identify this extractor. Leave blank and we'll generate one for you."
                optional={true}
                inputType="input"
                id="extractor_name"
                bind:value={name}
              />
              <FormElement
                label="Description"
                description="An optional description of this extractor."
                optional={true}
                inputType="textarea"
                id="extractor_description"
                bind:value={description}
              />
              <div class="font-medium">Prompt Options</div>
              <div class="text-sm text-gray-500">
                For multimodal extractors, you can specify prompts for each
                modality. Leave blank to use the default prompts.
              </div>
              <div class="flex flex-col gap-2">
                <FormElement
                  label="Document"
                  description="A prompt to use for extracting content from documents (e.g. PDFs, Word documents, etc.)."
                  optional={true}
                  inputType="textarea"
                  id="prompt_document"
                  bind:value={prompt_document}
                  placeholder="Transcribe the document into markdown."
                />
              </div>
              <div class="flex flex-col gap-2">
                <FormElement
                  label="Image"
                  description="A prompt to use for extracting content from images."
                  optional={true}
                  inputType="textarea"
                  id="prompt_image"
                  bind:value={prompt_image}
                  placeholder="Describe the image in markdown."
                />
              </div>
              <div class="flex flex-col gap-2">
                <FormElement
                  label="Video"
                  description="A prompt to use for extracting content from videos."
                  optional={true}
                  inputType="textarea"
                  id="prompt_video"
                  bind:value={prompt_video}
                  placeholder="Describe what happens in the video in markdown. Take into account the audio as well as the visual content. Your transcription must chronologically describe the events in the video and transcribe any speech."
                />
              </div>
              <div class="flex flex-col gap-2">
                <FormElement
                  label="Audio"
                  description="A prompt to use for extracting content from audio files."
                  optional={true}
                  inputType="textarea"
                  id="prompt_audio"
                  bind:value={prompt_audio}
                  placeholder="Transcribe the audio into markdown. If the audio contains speech, transcribe it into markdown."
                />
              </div>
            </div>
          </div>
        </div>
      </FormContainer>
    </div>
  {/if}
</AppPage>
