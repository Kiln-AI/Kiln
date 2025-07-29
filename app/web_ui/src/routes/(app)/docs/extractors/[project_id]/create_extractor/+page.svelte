<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { goto } from "$app/navigation"
  import AvailableModelsDropdown from "../../../../run/available_models_dropdown.svelte"
  import type { ModelProviderName } from "$lib/types"

  $: project_id = $page.params.project_id

  let loading: boolean = false
  let error: KilnError | null = null
  let name: string | null = null
  let description: string = ""
  let selected_extractor_option: string
  let output_format: "text/markdown" | "text/plain" = "text/markdown"
  let prompt_document: string | null = null
  let prompt_image: string | null = null
  let prompt_video: string | null = null
  let prompt_audio: string | null = null

  async function create_extractor_config() {
    try {
      loading = true

      const [model_provider_name, model_name] =
        selected_extractor_option.split("/")

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
            output_format: output_format,
            model_name: model_name,
            model_provider_name: model_provider_name as ModelProviderName,
            properties: {
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
        error = createKilnError(create_extractor_error)
        return
      }

      goto(`/docs/extractors/${project_id}`)
    } finally {
      loading = false
    }
  }
</script>

<AppPage
  title="Create Document Extractor"
  subtitle="A configuration for extracting data from your documents."
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else}
    <div class="max-w-[900px]">
      <FormContainer
        submit_visible={true}
        submit_label="Create Extractor"
        on:submit={create_extractor_config}
        {error}
        gap={4}
        bind:submitting={loading}
      >
        <div class="flex flex-col gap-4">
          <AvailableModelsDropdown
            label="Extraction Model"
            description="Select a model to use for extracting data from your documents."
            bind:model={selected_extractor_option}
            filter_models_predicate={(m) => m.supports_doc_extraction}
          />
          <FormElement
            label="Output Format"
            description="Which format should the extracted data be returned in?"
            inputType="select"
            id="output_format"
            bind:value={output_format}
            select_options={[
              ["text/markdown", "Markdown"],
              ["text/plain", "Plain Text"],
            ]}
          />
        </div>
        <div class="mt-4">
          <div class="collapse collapse-arrow bg-base-200">
            <input type="checkbox" class="peer" />
            <div class="collapse-title font-medium">Advanced Options</div>
            <div class="collapse-content flex flex-col gap-4">
              <div>
                <div class="font-medium">Prompt Options</div>
                <div class="text-sm text-gray-500 mt-1">
                  Specify the prompt which will be used to extract data from
                  your documents. Each document type has it's own prompt. Leave
                  blank to use the default.
                </div>
              </div>
              <div class="flex flex-col gap-2">
                <FormElement
                  label="Document Extraction Prompt"
                  description="A prompt used to extracting documents (e.g. PDFs, HTML, etc.)."
                  info_description="Typically something like 'Transcribe the document into markdown.' or 'Transcribe the document into plain text.'"
                  optional={true}
                  inputType="textarea"
                  id="prompt_document"
                  bind:value={prompt_document}
                  placeholder="Transcribe the document into markdown."
                />
              </div>
              <div class="flex flex-col gap-2">
                <FormElement
                  label="Image Extraction Prompt"
                  description="A prompt used to generate text descriptions of images."
                  info_description="Typically something like 'Describe the contents of the image in markdown.'"
                  optional={true}
                  inputType="textarea"
                  id="prompt_image"
                  bind:value={prompt_image}
                  placeholder="Describe the image in markdown."
                />
              </div>
              <div class="flex flex-col gap-2">
                <FormElement
                  label="Video Extraction Prompt"
                  description="A prompt used to generate text descriptions of videos."
                  info_description="Typically something like 'Describe what happens in the video in markdown. Take into account the audio as well as the visual content. Your transcription must chronologically describe the events in the video and transcribe any speech.'"
                  optional={true}
                  inputType="textarea"
                  id="prompt_video"
                  bind:value={prompt_video}
                  placeholder="Describe what happens in the video in markdown. Take into account the audio as well as the visual content. Your transcription must chronologically describe the events in the video and transcribe any speech."
                />
              </div>
              <div class="flex flex-col gap-2">
                <FormElement
                  label="Audio Extraction Prompt"
                  description="A prompt used to generate text descriptions of audio files."
                  info_description="Typically something like 'Transcribe the audio into markdown. If the audio contains speech, transcribe it into markdown.'"
                  optional={true}
                  inputType="textarea"
                  id="prompt_audio"
                  bind:value={prompt_audio}
                  placeholder="Transcribe the audio into markdown. If the audio contains speech, transcribe it into markdown."
                />
              </div>
              <div class="font-medium mt-6">Extractor Details</div>
              <FormElement
                label="Extractor Name"
                description="Leave blank and we'll generate one for you using the model name and output format."
                optional={true}
                inputType="input"
                id="extractor_name"
                bind:value={name}
              />
              <FormElement
                label="Description"
                description="A description of the extractor for you and your team. This will have no effect on the extractor's behavior."
                optional={true}
                inputType="textarea"
                id="extractor_description"
                bind:value={description}
              />
            </div>
          </div>
        </div>
      </FormContainer>
    </div>
  {/if}
</AppPage>
