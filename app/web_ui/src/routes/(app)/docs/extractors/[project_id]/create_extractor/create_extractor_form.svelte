<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import type {
    ModelProviderName,
    OutputFormat,
    ExtractorType,
  } from "$lib/types"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createEventDispatcher } from "svelte"
  import AvailableExtractorsDropdown from "./available_extractors_dropdown.svelte"
  import Collapse from "$lib/ui/collapse.svelte"

  $: project_id = $page.params.project_id

  let loading: boolean = false
  let error: KilnError | null = null
  let name: string | null = null
  let description: string = ""
  let selected_extractor: string = ""
  let extractor_type: "litellm" | "llama_pdf_reader" | null = null
  let model_provider_name: string | null = null
  let model_name: string | null = null
  let output_format: "text/markdown" | "text/plain" = "text/markdown"

  $: prompt_document = `Transcribe the document into ${output_format}.

If the document contains images and figures, describe them in the output. For example, if the
document contains an image, describe it in the output. If the document contains a table, format it 
appropriately and add a sentence describing it as a whole.

Format the output as valid ${output_format}.

Do NOT include any prefatory text such as 'Here is the transcription of the document:'.  
`

  $: prompt_image = `Describe the image in ${output_format}.

If the image contains text, transcribe it into ${output_format}.

Do NOT include any prefatory text such as 'Here is the description of the image:'.
`

  $: prompt_video = `Describe what happens in the video in ${output_format}.

Take into account the audio as well as the visual content. Your transcription must chronologically
describe the events in the video and transcribe any speech.

Do NOT include any prefatory text such as 'Here is the transcription of the video:'.
`

  $: prompt_audio = `Transcribe the document into ${output_format}.

If the document contains images and figures, describe them in the output. For example, if the
document contains an image, describe it in the output. If the document contains a table, format it 
appropriately and add a sentence describing it as a whole.

Format the output as valid ${output_format}.

Do NOT include any prefatory text such as 'Here is the transcription of the document:'.
`
  export let keyboard_submit: boolean = false

  const dispatch = createEventDispatcher<{
    success: { extractor_config_id: string }
  }>()

  async function create_extractor_config() {
    try {
      loading = true

      if (!extractor_type) {
        error = createKilnError({
          detail: "Please select an extractor type",
        })
        return
      }

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
            model_provider_name:
              extractor_type === "llama_pdf_reader"
                ? ""
                : (model_provider_name as ModelProviderName),
            model_name:
              extractor_type === "llama_pdf_reader" ? "" : model_name || "",
            output_format: output_format as OutputFormat,
            extractor_type: extractor_type as ExtractorType,
            properties:
              extractor_type === "litellm"
                ? {
                    model_name: model_name || "",
                    prompt_document: prompt_document || null,
                    prompt_image: prompt_image || null,
                    prompt_video: prompt_video || null,
                    prompt_audio: prompt_audio || null,
                  }
                : {},
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
    <AvailableExtractorsDropdown
      label="Extractor"
      description="The extractor to use to transform your documents into text."
      bind:extractor={selected_extractor}
      bind:extractor_type
      bind:provider_name={model_provider_name}
      bind:model_name
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
    {#if extractor_type === "litellm"}
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
    {:else if extractor_type === "llama_pdf_reader"}
      <div>
        <div class="font-medium">Llama PDF Reader</div>
        <div class="text-sm text-gray-500 mt-1">
          The Llama PDF Reader is a specialized extractor optimized for PDF
          documents. It provides high-quality text extraction without requiring
          an AI model or custom prompts.
        </div>
      </div>
    {/if}
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
