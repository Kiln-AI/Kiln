<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { provider_name_from_id } from "$lib/stores"

  let connected_providers: [string, string][] = []
  let loading_providers = true
  let error: KilnError | null = null
  let custom_models: string[] = []
  let new_model_provider: string | null = null
  let new_model_name: string | null = null

  const load_existing_providers = async () => {
    try {
      loading_providers = true
      connected_providers = []
      let { data: settings, error: settings_error } =
        await client.GET("/api/settings")
      if (settings_error) {
        throw settings_error
      }
      if (!settings) {
        throw new KilnError("Settings not found", null)
      }
      custom_models = settings["custom_models"] || []
      if (settings["open_ai_api_key"]) {
        connected_providers.push(["openai", "OpenAI"])
      }
      if (settings["groq_api_key"]) {
        connected_providers.push(["groq", "Groq"])
      }
      if (settings["bedrock_access_key"] && settings["bedrock_secret_key"]) {
        connected_providers.push(["bedrock", "AWS Bedrock"])
      }
      if (settings["open_router_api_key"]) {
        connected_providers.push(["openrouter", "OpenRouter"])
      }
      if (settings["fireworks_api_key"] && settings["fireworks_account_id"]) {
        connected_providers.push(["fireworks_ai", "Fireworks AI"])
      }
      // Skipping Ollama -- we pull all models from it automatically
      if (connected_providers.length > 0) {
        new_model_provider = connected_providers[0][0] || null
      } else {
        new_model_provider = null
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading_providers = false
    }
  }

  onMount(async () => {
    await load_existing_providers()
  })

  function remove_model(model_index: number) {
    custom_models = custom_models.filter((_, index) => index !== model_index)
    save_model_list()
  }

  function show_add_model_modal() {
    // @ts-expect-error showModal is not a method on HTMLElement
    document.getElementById("add_model_modal")?.showModal()
  }

  function add_model() {
    if (
      new_model_provider &&
      new_model_provider.length > 0 &&
      new_model_name &&
      new_model_name.length > 0
    ) {
      let model_id = new_model_provider + "::" + new_model_name
      custom_models = [...custom_models, model_id]
      save_model_list()
      new_model_name = null
    }

    // @ts-expect-error showModal is not a method on HTMLElement
    document.getElementById("add_model_modal")?.close()
  }

  let saving_model_list = false
  let save_model_list_error: KilnError | null = null
  async function save_model_list() {
    try {
      saving_model_list = true
      let { data: save_result, error: save_error } = await client.POST(
        "/api/settings",
        { body: { custom_models: custom_models } },
      )
      if (save_error) {
        throw save_error
      }
      if (!save_result) {
        throw new KilnError("No response from server", null)
      }
    } catch (e) {
      save_model_list_error = createKilnError(e)
    } finally {
      saving_model_list = false
    }
  }

  function get_model_name(model_id: string) {
    let [_, ...model_name_parts] = model_id.split("::")
    return model_name_parts.join("::")
  }

  function get_provider_name(model_id: string) {
    let [provider, ..._] = model_id.split("::")
    return provider_name_from_id(provider)
  }
</script>

<AppPage
  title="Add Models"
  sub_subtitle="Each AI provider already includes models tested for Kiln. Add additional models here."
  action_buttons={custom_models && custom_models.length > 0
    ? [
        {
          label: "Add Model",
          primary: true,
          handler: show_add_model_modal,
        },
      ]
    : []}
>
  {#if loading_providers}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if error}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="alert alert-error">
        <span>{error.message}</span>
      </div>
    </div>
  {:else if custom_models.length > 0}
    <div class="flex flex-col gap-4">
      {#each custom_models as model, index}
        <div class="flex flex-row gap-2 card bg-base-200 py-2 px-4">
          <div class="font-medium min-w-24">
            {get_provider_name(model)}
          </div>
          <div class="grow">
            {get_model_name(model)}
          </div>
          <button
            on:click={() => remove_model(index)}
            class="link text-sm text-gray-500">Remove</button
          >
        </div>
      {/each}
    </div>
  {:else}
    <div class="flex flex-col gap-4 justify-center items-center min-h-[30vh]">
      <button
        class="btn btn-wide btn-primary mt-4"
        on:click={show_add_model_modal}
      >
        Add Model
      </button>
    </div>
  {/if}
  {#if saving_model_list}
    <div class="flex flex-row gap-2 mt-4">
      <div class="loading loading-spinner"></div>
      Saving
    </div>
  {:else if save_model_list_error}
    <div class="alert alert-error">
      <span>Error saving model list: {save_model_list_error.message}</span>
    </div>
  {/if}
</AppPage>

<dialog id="add_model_modal" class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-bold">Add Model</h3>
    <div class="text-sm">Add a model from an existing provider.</div>
    <div class="text-sm text-gray-500 mt-3">
      Provide the exact model ID used by the provider API. For example, OpenAI's
      "gpt-3.5-turbo" or Groq's "gemma2-9b-it".
    </div>
    <div class="flex flex-col gap-4 mt-8">
      <FormElement
        label="Model Provider"
        id="model_provider"
        inputType="select"
        select_options={connected_providers}
        bind:value={new_model_provider}
      />
      <FormElement
        label="Model Name"
        id="model_name"
        inputType="input"
        bind:value={new_model_name}
      />
    </div>
    <div class="flex flex-row gap-6 justify-center flex-col mt-4">
      <button class="btn btn-primary" on:click={add_model}>Add Model</button>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
