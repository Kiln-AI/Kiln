<script lang="ts">
  import { fade } from "svelte/transition"
  import { onMount } from "svelte"
  import { _ } from "svelte-i18n"
  import type { OllamaConnection } from "$lib/types"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { client, base_url } from "$lib/api_client"
  import Warning from "$lib/ui/warning.svelte"
  import { available_tuning_models } from "$lib/stores/fine_tune_store"

  export let highlight_finetune = false

  type Provider = {
    name: string
    id: string
    description: string
    image: string
    featured: boolean
    pill_text?: string
    api_key_steps?: string[]
    api_key_warning?: string
    api_key_fields?: string[]
    optional_fields?: string[]
  }
  const providers: Provider[] = [
    {
      name: "OpenRouter.ai",
      id: "openrouter",
      description: "",
      image: "/images/openrouter.svg",
      featured: !highlight_finetune,
    },
    {
      name: "OpenAI",
      id: "openai",
      description: "",
      image: "/images/openai.svg",
      featured: false,
      pill_text: highlight_finetune
        ? $_("providers.connect_providers.pills.tuneable")
        : undefined,
    },
    {
      name: "Ollama",
      id: "ollama",
      description: "",
      image: "/images/ollama.svg",
      featured: false,
    },
    {
      name: "Groq",
      id: "groq",
      description: "",
      image: "/images/groq.svg",
      featured: false,
    },
    {
      name: "Fireworks AI",
      id: "fireworks_ai",
      description: "",
      image: "/images/fireworks.svg",
      pill_text: highlight_finetune
        ? $_("providers.connect_providers.pills.tuneable")
        : undefined,
      featured: false,
      api_key_fields: [
        $_("providers.connect_providers.api_key_fields.api_key"),
        $_("providers.connect_providers.api_key_fields.account_id"),
      ],
    },
    {
      name: "Anthropic",
      id: "anthropic",
      description: "",
      image: "/images/anthropic.svg",
      featured: false,
      api_key_fields: [
        $_("providers.connect_providers.api_key_fields.api_key"),
      ],
    },
    {
      name: "Gemini AI Studio",
      id: "gemini_api",
      description: "",
      image: "/images/gemini.svg",
      featured: false,
      api_key_fields: [
        $_("providers.connect_providers.api_key_fields.api_key"),
      ],
    },
    {
      name: "Azure OpenAI",
      id: "azure_openai",
      description: "",
      image: "/images/azure_openai.svg",
      featured: false,
      api_key_fields: [
        $_("providers.connect_providers.api_key_fields.api_key"),
        $_("providers.connect_providers.api_key_fields.endpoint_url"),
      ],
    },
    {
      name: "Hugging Face",
      id: "huggingface",
      description: "",
      image: "/images/hugging_face.svg",
      featured: false,
      api_key_fields: [
        $_("providers.connect_providers.api_key_fields.api_key"),
      ],
    },
    {
      name: "Google Vertex AI",
      id: "vertex",
      description: "",
      image: "/images/google_logo.svg",
      featured: false,
      pill_text: highlight_finetune
        ? $_("providers.connect_providers.pills.tuneable")
        : undefined,
      api_key_fields: [
        $_("providers.connect_providers.api_key_fields.project_id"),
        $_("providers.connect_providers.api_key_fields.project_location"),
      ],
    },
    {
      name: "Together.ai",
      id: "together_ai",
      description: "",
      image: "/images/together_ai.svg",
      featured: false,
      pill_text: highlight_finetune
        ? $_("providers.connect_providers.pills.tuneable")
        : undefined,
      api_key_fields: [
        $_("providers.connect_providers.api_key_fields.api_key"),
      ],
    },
    {
      name: "Amazon Bedrock",
      id: "amazon_bedrock",
      description: "",
      image: "/images/aws.svg",
      featured: false,
      api_key_fields: [
        $_("providers.connect_providers.api_key_fields.access_key"),
        $_("providers.connect_providers.api_key_fields.secret_key"),
      ],
    },
    {
      name: "Weights & Biases",
      id: "wandb",
      description: "",
      image: "/images/wandb.svg",
      featured: false,
      api_key_fields: [
        $_("providers.connect_providers.api_key_fields.api_key"),
        $_("providers.connect_providers.api_key_fields.base_url"),
      ],
      optional_fields: [
        $_("providers.connect_providers.api_key_fields.base_url"),
      ],
    },
    {
      name: "Custom API",
      id: "openai_compatible",
      description: "",
      image: "/images/api.svg",
      featured: false,
    },
  ]

  type ProviderStatus = {
    connected: boolean
    error: string | null
    custom_description: string | null
    connecting: boolean
  }
  let status: { [key: string]: ProviderStatus } = {
    ollama: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    openai: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    openrouter: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    groq: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    amazon_bedrock: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    fireworks_ai: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    anthropic: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    vertex: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    gemini_api: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    huggingface: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    azure_openai: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    together_ai: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    openai_compatible: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
    wandb: {
      connected: false,
      connecting: false,
      error: null,
      custom_description: null,
    },
  }

  export let has_connected_providers = false
  $: has_connected_providers = Object.values(status).some(
    (provider) => provider.connected,
  )
  export let intermediate_step = false
  let api_key_provider: Provider | null = null
  $: {
    intermediate_step = api_key_provider != null
  }

  // Computed properties for translations
  let api_key_steps: string[] = []
  $: api_key_steps = api_key_provider
    ? ($_(`providers.connect_providers.api_key_steps.${api_key_provider.id}`, {
        default: "",
      }) as unknown as string[]) || []
    : []
  $: api_key_warning = api_key_provider
    ? ($_(
        `providers.connect_providers.provider_warnings.${api_key_provider.id}`,
        { default: "" },
      ) as string)
    : ""

  const disconnect_provider = async (provider: Provider) => {
    if (provider.id === "ollama") {
      alert($_("providers.connect_providers.ollama_disconnect_message"))
      return
    }
    if (!confirm($_("providers.connect_providers.disconnect_confirm"))) {
      return
    }
    try {
      const { error: disconnect_error } = await client.POST(
        "/api/provider/disconnect_api_key",
        {
          params: {
            query: {
              provider_id: provider.id,
            },
          },
        },
      )
      if (disconnect_error) {
        throw disconnect_error
      }

      status[provider.id].connected = false

      // Clear the available models list
      available_tuning_models.set(null)
    } catch (e) {
      console.error("disconnect_provider error", e)
      alert($_("providers.connect_providers.disconnect_failed"))
      return
    }
  }

  const connect_provider = (provider: Provider) => {
    if (status[provider.id].connected) {
      return
    }
    if (provider.id === "ollama") {
      connect_ollama()
    }
    if (provider.id === "openai_compatible") {
      show_custom_api_dialog()
    }

    if (provider.api_key_steps) {
      api_key_provider = provider
    }
  }

  let custom_ollama_url: string | null = null

  const connect_ollama = async (user_initated: boolean = true) => {
    status.ollama.connected = false
    status.ollama.connecting = user_initated

    let data: OllamaConnection | null = null
    try {
      const { data: req_data, error: req_error } = await client.GET(
        "/api/provider/ollama/connect",
        {
          params: {
            query: {
              custom_ollama_url: custom_ollama_url || undefined,
            },
          },
        },
      )
      if (req_error) {
        throw req_error
      }
      data = req_data
    } catch (e) {
      if (
        e &&
        typeof e === "object" &&
        "message" in e &&
        typeof e.message === "string"
      ) {
        status.ollama.error = e.message
      } else {
        status.ollama.error = $_(
          "providers.connect_providers.ollama_connection_failed",
        )
      }
      status.ollama.connected = false
      return
    } finally {
      status.ollama.connecting = false
    }
    // Check min version number. We require 0.5+ for structured output
    if (data.version) {
      const version_parts = data.version.split(".")
      if (version_parts.length >= 2) {
        const major = parseInt(version_parts[0])
        const minor = parseInt(version_parts[1])
        if (major < 0 || (major == 0 && minor < 5)) {
          status.ollama.error = $_(
            "providers.connect_providers.ollama_version_error",
          )
          status.ollama.connected = false
          return
        }
      }
    }
    if (
      data.supported_models.length === 0 &&
      (!data.untested_models || data.untested_models.length === 0)
    ) {
      status.ollama.error = $_("providers.connect_providers.ollama_no_models")
      return
    }
    status.ollama.error = null
    status.ollama.connected = true
    const supported_models_str =
      data.supported_models.length > 0
        ? $_("providers.connect_providers.ollama_supported_models", {
            values: { models: data.supported_models.join(", ") },
          }) + " "
        : $_("providers.connect_providers.ollama_no_supported_models") + " "
    const untested_models_str =
      data.untested_models && data.untested_models.length > 0
        ? $_("providers.connect_providers.ollama_untested_models", {
            values: { models: data.untested_models.join(", ") },
          }) + " "
        : ""
    const custom_url_str =
      custom_ollama_url && custom_ollama_url == "http://localhost:11434"
        ? ""
        : $_("providers.connect_providers.ollama_custom_url", {
            values: { url: custom_ollama_url },
          })
    status.ollama.custom_description =
      $_("providers.connect_providers.ollama_connected") +
      " " +
      supported_models_str +
      untested_models_str +
      custom_url_str
  }

  let api_key_issue = false
  let api_key_submitting = false
  let api_key_message: string | null = null
  const submit_api_key = async () => {
    const apiKeyFields = document.getElementById(
      "api-key-fields",
    ) as HTMLDivElement
    const inputs = apiKeyFields.querySelectorAll("input")
    const apiKeyData: Record<string, string> = {}
    for (const input of inputs) {
      apiKeyData[input.id] = input.value
      if (!input.value) {
        if (api_key_provider?.optional_fields?.includes(input.id)) {
          delete apiKeyData[input.id]
        } else {
          api_key_issue = true
          return
        }
      }
    }

    api_key_issue = false
    api_key_message = null
    api_key_submitting = true
    try {
      const provider_id = api_key_provider ? api_key_provider.id : ""
      let res = await fetch(base_url + "/api/provider/connect_api_key", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          provider: provider_id,
          key_data: apiKeyData,
        }),
      })
      let data = await res.json()

      if (res.status !== 200) {
        api_key_message =
          data.message || $_("providers.connect_providers.disconnect_failed")
        return
      }

      api_key_issue = false
      api_key_message = null
      status[provider_id].connected = true
      api_key_provider = null

      // Clear the available models list
      available_tuning_models.set(null)
    } catch (e) {
      console.error("submit_api_key error", e)
      api_key_message =
        $_("providers.connect_providers.disconnect_failed") +
        " (Exception: " +
        e +
        ")"
      api_key_issue = true
      return
    } finally {
      api_key_submitting = false
    }
  }

  let loading_initial_providers = true
  let initial_load_failure = false
  type CustomOpenAICompatibleProvider = {
    name: string
    base_url: string
    api_key: string
  }
  let custom_openai_compatible_providers: CustomOpenAICompatibleProvider[] = []
  const check_existing_providers = async () => {
    try {
      let res = await fetch(base_url + "/api/settings")
      let data = await res.json()
      if (data["open_ai_api_key"]) {
        status.openai.connected = true
      }
      if (data["groq_api_key"]) {
        status.groq.connected = true
      }
      if (data["bedrock_access_key"] && data["bedrock_secret_key"]) {
        status.amazon_bedrock.connected = true
      }
      if (data["open_router_api_key"]) {
        status.openrouter.connected = true
      }
      if (data["fireworks_api_key"] && data["fireworks_account_id"]) {
        status.fireworks_ai.connected = true
      }
      if (data["vertex_project_id"] && data["vertex_location"]) {
        status.vertex.connected = true
      }
      if (data["ollama_base_url"]) {
        custom_ollama_url = data["ollama_base_url"]
      }
      if (data["anthropic_api_key"]) {
        status.anthropic.connected = true
      }
      if (data["gemini_api_key"]) {
        status.gemini_api.connected = true
      }
      if (data["azure_openai_api_key"] && data["azure_openai_endpoint"]) {
        status.azure_openai.connected = true
      }
      if (data["huggingface_api_key"]) {
        status.huggingface.connected = true
      }
      if (data["together_api_key"]) {
        status.together_ai.connected = true
      }
      if (data["wandb_api_key"]) {
        status.wandb.connected = true
      }
      if (
        data["openai_compatible_providers"] &&
        data["openai_compatible_providers"].length > 0
      ) {
        status.openai_compatible.connected = true
        custom_openai_compatible_providers = data["openai_compatible_providers"]
      }
    } catch (e) {
      console.error("check_existing_providers error", e)
      initial_load_failure = true
    } finally {
      loading_initial_providers = false
    }
  }

  onMount(async () => {
    await check_existing_providers()
    // Check Ollama every load, as it can be closed. More epmemerial (and local/cheap/fast)
    connect_ollama(false).then(() => {
      // Clear the error as the user didn't initiate this run
      status["ollama"].error = null
    })
  })

  function show_custom_ollama_url_dialog() {
    // @ts-expect-error showModal is not a method on HTMLElement
    document.getElementById("ollama_dialog")?.showModal()
  }

  function show_custom_api_dialog() {
    // @ts-expect-error showModal is not a method on HTMLElement
    document.getElementById("openai_compatible_dialog")?.showModal()
  }

  let new_provider_name = ""
  let new_provider_base_url = ""
  let new_provider_api_key = ""
  let adding_new_provider = false
  let new_provider_error: KilnError | null = null
  async function add_new_provider() {
    try {
      adding_new_provider = true
      if (!new_provider_base_url.startsWith("http")) {
        throw new Error($_("providers.connect_providers.base_url_error"))
      }

      const { error: save_error } = await client.POST(
        "/api/provider/openai_compatible",
        {
          params: {
            query: {
              name: new_provider_name,
              base_url: new_provider_base_url,
              api_key: new_provider_api_key,
            },
          },
        },
      )
      if (save_error) {
        throw save_error
      }

      // Refresh to trigger the UI update
      custom_openai_compatible_providers = [
        ...custom_openai_compatible_providers,
        {
          name: new_provider_name,
          base_url: new_provider_base_url,
          api_key: new_provider_api_key,
        },
      ]

      // Reset the form
      new_provider_name = ""
      new_provider_base_url = ""
      new_provider_api_key = ""
      new_provider_error = null

      status.openai_compatible.connected = true
      // @ts-expect-error daisyui does not add types
      document.getElementById("openai_compatible_dialog")?.close()
    } catch (e) {
      new_provider_error = createKilnError(e)
    } finally {
      adding_new_provider = false
    }
  }

  async function remove_openai_compatible_provider_at_index(index: number) {
    if (index < 0 || index >= custom_openai_compatible_providers.length) {
      return
    }
    try {
      let provider = custom_openai_compatible_providers[index]

      const { error: delete_error } = await client.DELETE(
        "/api/provider/openai_compatible",
        {
          params: {
            query: {
              name: provider.name,
            },
          },
        },
      )
      if (delete_error) {
        throw delete_error
      }

      // Update UI
      custom_openai_compatible_providers =
        custom_openai_compatible_providers.filter(
          (v, _) => v.name !== provider.name,
        )
      if (custom_openai_compatible_providers.length === 0) {
        status.openai_compatible.connected = false
      }
    } catch (e) {
      alert(
        $_("providers.connect_providers.remove_provider_failed", {
          values: { error: String(e) },
        }),
      )
    }
  }
</script>

<div class="w-full">
  {#if api_key_provider}
    <div class="grow h-full max-w-[400px] flex flex-col place-content-center">
      <div class="grow"></div>

      <h1 class="text-xl font-medium flex-none text-center">
        {$_("providers.connect_providers.connect_title", {
          values: { provider: api_key_provider.name },
        })}
      </h1>

      {#if api_key_warning !== ""}
        <div class="pt-2">
          <Warning
            warning_color="warning"
            warning_message={api_key_warning}
            trusted={true}
          />
        </div>
      {/if}

      <ol class="flex-none my-2 text-gray-700">
        {#each api_key_steps as step}
          <li class="list-decimal pl-1 mx-8 my-4">
            <!-- eslint-disable-next-line svelte/no-at-html-tags -->
            {@html step.replace(
              /https?:\/\/\S+/g,
              '<a href="$&" class="link underline" target="_blank">$&</a>',
            )}
          </li>
        {/each}
      </ol>
      {#if api_key_message}
        <p class="text-error text-center pb-4">{api_key_message}</p>
      {/if}
      <div class="flex flex-row gap-4 items-center">
        <div class="grow flex flex-col gap-2" id="api-key-fields">
          {#each api_key_provider.api_key_fields || [$_("providers.connect_providers.api_key_fields.api_key")] as field}
            <input
              type="text"
              id={field}
              placeholder={field}
              class="input input-bordered w-full max-w-[300px] {api_key_issue
                ? 'input-error'
                : ''}"
            />
          {/each}
        </div>
        <button
          class="btn min-w-[130px]"
          on:click={submit_api_key}
          disabled={api_key_submitting}
        >
          {#if api_key_submitting}
            <div class="loading loading-spinner loading-md"></div>
          {:else}
            {$_("providers.connect_providers.connect")}
          {/if}
        </button>
      </div>
      <button
        class="link text-center text-sm mt-8"
        on:click={() => (api_key_provider = null)}
      >
        {$_("providers.connect_providers.cancel_setup", {
          values: { provider: api_key_provider.name },
        })}
      </button>
      <div class="grow-[1.5]"></div>
    </div>
  {:else}
    <div
      class="w-full grid grid-cols-1 xl:grid-cols-2 gap-y-6 gap-x-24 max-w-lg xl:max-w-screen-xl"
    >
      {#each providers as provider}
        {@const is_connected =
          status[provider.id] && status[provider.id].connected}
        <div class="flex flex-row gap-4 items-center">
          <img
            src={provider.image}
            alt={provider.name}
            class="flex-none p-1 {provider.featured
              ? 'size-12'
              : 'size-10 mx-1'}"
          />
          <div class="flex flex-col grow pr-4">
            <h3
              class={provider.featured
                ? "text-large font-bold"
                : "text-base font-medium"}
            >
              {provider.name}
              {#if provider.featured}
                <div class="badge badge-sm ml-2 badge-secondary">
                  {$_("common.recommended")}
                </div>
              {:else if provider.pill_text}
                <div class="badge badge-sm ml-2 badge-primary">
                  {provider.pill_text}
                </div>
              {/if}
            </h3>
            {#if status[provider.id] && status[provider.id].error}
              <p class="text-sm text-error" in:fade>
                {status[provider.id].error}
              </p>
            {:else}
              <p class="text-sm text-gray-500">
                {status[provider.id].custom_description ||
                  $_(
                    `providers.connect_providers.provider_descriptions.${provider.id}`,
                    { default: provider.description },
                  )}
              </p>
            {/if}
            {#if provider.id === "ollama" && status[provider.id] && status[provider.id].error}
              <button
                class="link text-left text-sm text-gray-500"
                on:click={show_custom_ollama_url_dialog}
              >
                {$_("providers.connect_providers.set_custom_ollama_url")}
              </button>
            {/if}
          </div>

          {#if loading_initial_providers}
            <!-- Light loading state-->
            <div class="btn md:min-w-[100px] skeleton bg-base-200"></div>
            &nbsp;
          {:else if is_connected && provider.id === "openai_compatible"}
            <button
              class="btn md:min-w-[100px]"
              on:click={() => show_custom_api_dialog()}
            >
              {$_("providers.connect_providers.manage")}
            </button>
          {:else if is_connected}
            <button
              class="btn md:min-w-[100px] hover:btn-error group"
              on:click={() => disconnect_provider(provider)}
            >
              <img
                src="/images/circle-check.svg"
                class="size-6 group-hover:hidden"
                alt={$_("providers.connect_providers.connected")}
              />
              <span class="text-xs hidden group-hover:inline"
                >{$_("providers.connect_providers.disconnect")}</span
              >
            </button>
          {:else if status[provider.id].connecting}
            <div class="btn md:min-w-[100px]">
              <div class=" loading loading-spinner loading-md"></div>
            </div>
          {:else if initial_load_failure}
            <div>
              <div class="btn md:min-w-[100px] btn-error text-xs">
                {$_("providers.connect_providers.error")}
              </div>
              <div class="text-xs text-gray-500 text-center pt-1">
                {$_("providers.connect_providers.reload_page")}
              </div>
            </div>
          {:else}
            <button
              class="btn md:min-w-[100px]"
              on:click={() => connect_provider(provider)}
            >
              {$_("providers.connect_providers.connect")}
            </button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<dialog id="ollama_dialog" class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>

    <h3 class="text-lg font-bold">
      {$_("providers.connect_providers.custom_ollama_url")}
    </h3>
    <p class="text-sm font-light mb-8">
      {$_("providers.connect_providers.custom_ollama_url_description")}
    </p>
    <FormElement
      id="ollama_url"
      label={$_("providers.connect_providers.custom_ollama_url")}
      info_description={$_("providers.connect_providers.ollama_url_info")}
      bind:value={custom_ollama_url}
      placeholder="http://localhost:11434"
    />
    <div class="flex flex-row gap-4 items-center mt-4 justify-end">
      <form method="dialog">
        <button class="btn">{$_("common.cancel")}</button>
      </form>
      <button
        class="btn btn-primary"
        disabled={!custom_ollama_url}
        on:click={() => {
          connect_ollama(true)
          // @ts-expect-error showModal is not a method on HTMLElement
          document.getElementById("ollama_dialog")?.close()
        }}
      >
        {$_("providers.connect_providers.connect")}
      </button>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>{$_("common.close")}</button>
  </form>
</dialog>

<dialog id="openai_compatible_dialog" class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>

    <h3 class="text-lg font-bold flex flex-row gap-4">
      {$_("providers.connect_providers.connect_custom_apis")}
    </h3>
    <p class="text-sm font-light mb-8">
      {$_("providers.connect_providers.custom_api_description")}
    </p>
    {#if custom_openai_compatible_providers.length > 0}
      <div class="flex flex-col gap-2">
        <div class="font-medium">
          {$_("providers.connect_providers.existing_apis")}
        </div>
        {#each custom_openai_compatible_providers as provider, index}
          <div class="flex flex-row gap-3 card bg-base-200 px-4 items-center">
            <div class="text-sm">{provider.name}</div>
            <div class="text-sm text-gray-500 grow truncate">
              {provider.base_url}
            </div>
            <button
              class="btn btn-sm btn-ghost"
              on:click={() => remove_openai_compatible_provider_at_index(index)}
            >
              {$_("providers.connect_providers.remove")}
            </button>
          </div>
        {/each}
      </div>
    {/if}
    <div class="flex flex-col gap-2 mt-8">
      <div class="font-medium">
        {$_("providers.connect_providers.add_new_api")}
      </div>
      <FormContainer
        submit_label={$_("providers.connect_providers.add")}
        on:submit={add_new_provider}
        gap={2}
        submitting={adding_new_provider}
        error={new_provider_error}
      >
        <FormElement
          id="name"
          label={$_("providers.connect_providers.api_name")}
          bind:value={new_provider_name}
          placeholder={$_("providers.connect_providers.api_name_placeholder")}
          info_description={$_("providers.connect_providers.api_name_info")}
        />
        <FormElement
          id="base_url"
          label={$_("providers.connect_providers.base_url")}
          bind:value={new_provider_base_url}
          placeholder={$_("providers.connect_providers.base_url_placeholder")}
          info_description={$_("providers.connect_providers.base_url_info")}
        />
        <FormElement
          id="api_key"
          label={$_("providers.connect_providers.api_key")}
          optional={true}
          bind:value={new_provider_api_key}
          placeholder={$_("providers.connect_providers.api_key_placeholder")}
          info_description={$_("providers.connect_providers.api_key_info")}
        />
      </FormContainer>
    </div>

    <form method="dialog" class="modal-backdrop">
      <button>{$_("common.close")}</button>
    </form>
  </div>
</dialog>
