<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { provider_name_from_id } from "$lib/stores"
  import Dialog from "$lib/ui/dialog.svelte"
  import { _ } from "svelte-i18n"

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
        throw new KilnError($_("providers.settings_not_found"), null)
      }
      custom_models = settings["custom_models"] || []
      if (settings["open_ai_api_key"]) {
        connected_providers.push(["openai", "OpenAI"])
      }
      if (settings["groq_api_key"]) {
        connected_providers.push(["groq", "Groq"])
      }
      if (settings["bedrock_access_key"] && settings["bedrock_secret_key"]) {
        connected_providers.push(["amazon_bedrock", "AWS Bedrock"])
      }
      if (settings["open_router_api_key"]) {
        connected_providers.push(["openrouter", "OpenRouter"])
      }
      if (settings["fireworks_api_key"] && settings["fireworks_account_id"]) {
        connected_providers.push(["fireworks_ai", "Fireworks AI"])
      }
      if (settings["vertex_project_id"] && settings["vertex_location"]) {
        connected_providers.push(["vertex", "Vertex AI"])
      }
      if (settings["anthropic_api_key"]) {
        connected_providers.push(["anthropic", "Anthropic"])
      }
      if (settings["gemini_api_key"]) {
        connected_providers.push(["gemini_api", "Gemini"])
      }
      if (
        settings["azure_openai_api_key"] &&
        settings["azure_openai_endpoint"]
      ) {
        connected_providers.push(["azure_openai", "Azure OpenAI"])
      }
      if (settings["huggingface_api_key"]) {
        connected_providers.push(["huggingface", "Hugging Face"])
      }
      if (settings["together_api_key"]) {
        connected_providers.push(["together_ai", "Together AI"])
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

  let add_model_dialog: Dialog | null = null

  function show_add_model_modal() {
    add_model_dialog?.show()
  }

  async function add_model() {
    if (
      new_model_provider &&
      new_model_provider.length > 0 &&
      new_model_name &&
      new_model_name.length > 0
    ) {
      let model_id = new_model_provider + "::" + new_model_name
      custom_models = [...custom_models, model_id]
      await save_model_list()
      new_model_name = null
    } else {
      throw new KilnError($_("providers.invalid_model_error"), null)
    }

    return true
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
        throw new KilnError($_("providers.no_response_error"), null)
      }
    } catch (e) {
      save_model_list_error = createKilnError(e)
      // Re-throw the error so the dialog can can show it
      throw save_model_list_error
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
  title={$_("providers.add_models")}
  sub_subtitle={$_("providers.add_models_subtitle")}
  action_buttons={custom_models && custom_models.length > 0
    ? [
        {
          label: $_("providers.add_model"),
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
            class="link text-sm text-gray-500">{$_("common.remove")}</button
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
        {$_("providers.add_model")}
      </button>
    </div>
  {/if}
  {#if saving_model_list}
    <div class="flex flex-row gap-2 mt-4">
      <div class="loading loading-spinner"></div>
      {$_("providers.saving")}
    </div>
  {:else if save_model_list_error}
    <div class="mt-4 text-error font-medium">
      <span
        >{$_("providers.error_saving_model_list")}
        {save_model_list_error.message}</span
      >
    </div>
  {/if}
</AppPage>

<Dialog
  bind:this={add_model_dialog}
  title={$_("providers.add_model")}
  action_buttons={[
    { label: $_("common.cancel"), isCancel: true },
    {
      label: $_("providers.add_model"),
      asyncAction: add_model,
      disabled: !new_model_provider || !new_model_name,
      isPrimary: true,
    },
  ]}
>
  <div class="text-sm">{$_("providers.add_model_from_provider")}</div>
  <div class="text-sm text-gray-500 mt-3">
    {$_("providers.model_id_instructions")}
  </div>
  <div class="flex flex-col gap-4 mt-8">
    <FormElement
      label={$_("providers.model_provider")}
      id="model_provider"
      inputType="select"
      select_options={connected_providers}
      bind:value={new_model_provider}
    />
    <FormElement
      label={$_("providers.model_name")}
      id="model_name"
      inputType="input"
      bind:value={new_model_name}
    />
  </div>
</Dialog>
