<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "../../../../../../lib/api_client"
  import type { ExtractorType, OutputFormat } from "../../../../../../lib/types"
  import { createKilnError } from "../../../../../../lib/utils/error_handlers"
  import FormElement from "../../../../../../lib/utils/form_element.svelte"
  import AppPage from "../../../../app_page.svelte"

  $: project_id = $page.params.project_id

  let extractor_options = [
    {
      label: "Gemini: Gemini 2.0 Flash",
      value: "gemini:::gemini-2.0-flash",
    },
    {
      label: "Gemini: Gemini 2.0 Flash Lite",
      value: "gemini:::gemini-2.0-flash-lite",
    },
  ]

  let loading: boolean = false
  let name: string = ""
  let description: string = ""
  let selected_extractor_option: string = extractor_options[0].value
  let output_format: "text/markdown" | "text/plain" = "text/markdown"
  let prompt_document: string | null = null
  let prompt_image: string | null = null
  let prompt_video: string | null = null
  let prompt_audio: string | null = null

  $: extractor_type = selected_extractor_option.split(":::")[0]
  $: model_name = selected_extractor_option.split(":::")[1]

  async function create_processor() {
    try {
      loading = true
      const { error: post_error } = await client.POST(
        "/api/projects/{project_id}/create_extractor_config",
        {
          params: {
            path: {
              project_id,
            },
          },
          body: {
            name,
            description,
            extractor_type: extractor_type as unknown as ExtractorType,
            output_format: output_format as unknown as OutputFormat,
            properties: {
              model_name,
              prompt_for_kind: {
                document: prompt_document || "",
                image: prompt_image || "",
                video: prompt_video || "",
                audio: prompt_audio || "",
              },
            },
            passthrough_mimetypes: ["text/plain", "text/markdown"],
          },
        },
      )

      if (post_error) {
        throw createKilnError(post_error)
      }
    } finally {
      loading = false
    }
  }
</script>

<AppPage
  title="Create Processor"
  sub_subtitle="Create a new processor"
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
          <div class="collapse-title font-medium">Advanced Options</div>
          <div class="collapse-content flex flex-col gap-4">
            <FormElement
              label="Name"
              description="A name to identify this processor. Leave blank and we'll generate one for you."
              optional={true}
              inputType="input"
              id="processor_name"
              bind:value={name}
            />
            <FormElement
              label="Description"
              description="An optional description of this processor."
              optional={true}
              inputType="textarea"
              id="processor_description"
              bind:value={description}
            />
            <div class="font-medium">Prompt options</div>
            <div class="flex flex-col gap-2">
              <FormElement
                label="Document"
                description="A prompt to use for document processing."
                optional={true}
                inputType="textarea"
                id="prompt_document"
                bind:value={prompt_document}
                placeholder="Transcribe the document into markdown."
              />
            </div>
          </div>
        </div>
      </div>

      <button class="mt-4 btn btn-primary" on:click={create_processor}>
        Create Processor
      </button>
    </div>
  {/if}
</AppPage>
