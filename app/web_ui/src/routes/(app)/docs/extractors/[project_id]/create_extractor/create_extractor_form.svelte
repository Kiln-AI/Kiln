<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import type { ModelProviderName, OutputFormat } from "$lib/types"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createEventDispatcher } from "svelte"
  import AvailableModelsDropdown from "$lib/ui/available_models_dropdown.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import { ui_state } from "$lib/stores"
  import {
    default_extractor_document_prompts,
    default_extractor_image_prompts,
    default_extractor_video_prompts,
    default_extractor_audio_prompts,
  } from "./default_extractor_prompts"

  $: project_id = $page.params.project_id

  let loading: boolean = false
  let error: KilnError | null = null
  let name: string | null = null
  let description: string = ""
  let selected_extractor_option: string
  let output_format: "text/markdown" | "text/plain" = "text/markdown"

  $: prompt_document = default_extractor_document_prompts(output_format)
  $: prompt_image = default_extractor_image_prompts(output_format)
  $: prompt_video = default_extractor_video_prompts(output_format)
  $: prompt_audio = default_extractor_audio_prompts(output_format)

  export let keyboard_submit: boolean = false

  const dispatch = createEventDispatcher<{
    success: { extractor_config_id: string }
  }>()

  async function create_extractor_config() {
    try {
      loading = true

      const [model_provider_name, model_name] =
        selected_extractor_option.split("/")

      const { error: create_extractor_error, data } = await client.POST(
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
            model_provider_name: model_provider_name as ModelProviderName,
            model_name: model_name,
            output_format: output_format as OutputFormat,
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
        error = createKilnError(create_extractor_error)
        return
      }

      dispatch("success", { extractor_config_id: data.id || "" })
    } finally {
      loading = false
    }
  }
</script>

<FormContainer
  submit_visible={true}
  submit_label="Create Extractor"
  on:submit={async (_) => {
    await create_extractor_config()
  }}
  {error}
  gap={4}
  bind:submitting={loading}
  {keyboard_submit}
>
  <div class="flex flex-col gap-4">
    <AvailableModelsDropdown
      task_id={$ui_state.current_task_id ?? ""}
      label="Extraction Model"
      description="The model to use to transform your documents into text."
      info_description="Files like PDFs, audio and video must be converted to text before they can be indexed and searched. This model extracts text from these files."
      bind:model={selected_extractor_option}
      filter_models_predicate={(m) => m.supports_doc_extraction}
      suggested_mode="doc_extraction"
    />
    <FormElement
      label="Output Format"
      description="The text format the extraction model will generate."
      info_description="Markdown is a text format which includes basic formatting (headers, links, tables, etc). Plaintext will not include any formatting information."
      inputType="fancy_select"
      id="output_format"
      bind:value={output_format}
      fancy_select_options={[
        {
          options: [
            {
              label: "Markdown",
              value: "text/markdown",
              badge: "Recommended",
            },

            {
              label: "Plain Text",
              value: "text/plain",
            },
          ],
        },
      ]}
    />
  </div>
  <Collapse title="Advanced Options">
    <div>
      <div class="font-medium">Prompt Options</div>
      <div class="text-sm text-gray-500 mt-1">
        Specify the prompt which will be used to extract data from your
        documents. Each document type has it's own prompt. Leave blank to use
        the default.
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
      description="A name to identify this extractor. Leave blank and we'll generate one for you."
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
  </Collapse>
</FormContainer>
