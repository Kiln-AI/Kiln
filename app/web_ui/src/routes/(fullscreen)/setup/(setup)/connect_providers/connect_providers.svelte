<script lang="ts">
  import { fade } from "svelte/transition"
  import { onMount } from "svelte"
  import { client } from "$lib/api_client"
  import type { OllamaConnection } from "$lib/types"
  import FormElement from "$lib/utils/form_element.svelte"

  type Provider = {
    name: string
    id: string
    description: string
    image: string
    featured: boolean
    api_key_steps?: string[]
    api_key_warning?: string
    api_key_fields?: string[]
  }
  const providers: Provider[] = [
    {
      name: "OpenRouter.ai",
      id: "openrouter",
      description:
        "Proxies requests to OpenAI, Anthropic, and more. Works with almost any model.",
      image: "/images/openrouter.svg",
      featured: true,
      api_key_steps: [
        "Go to https://openrouter.ai/settings/keys",
        "Create a new API Key",
        "Copy the new API Key, paste it below and click 'Connect'",
      ],
    },
    {
      name: "OpenAI",
      id: "openai",
      description: "The OG home to GPT-4 and more. Supports fine-tuning.",
      image: "/images/openai.svg",
      featured: false,
      api_key_steps: [
        "Go to https://platform.openai.com/account/api-keys",
        "Click 'Create new secret key'",
        "Copy the new secret key, paste it below and click 'Connect'",
      ],
    },
    {
      name: "Ollama",
      id: "ollama",
      description: "Run models locally. No API key required.",
      image: "/images/ollama.svg",
      featured: false,
    },
    {
      name: "Groq",
      id: "groq",
      description:
        "The fastest model host. Providing Llama, Gemma and Mistral models.",
      image: "/images/groq.svg",
      featured: false,
      api_key_steps: [
        "Go to https://console.groq.com/keys",
        "Create an API Key",
        "Copy the new key, paste it below and click 'Connect'",
      ],
    },
    {
      name: "Fireworks AI",
      id: "fireworks_ai",
      description: "Open models (Llama, Phi), plus the ability to fine-tune.",
      image: "/images/fireworks.svg",
      api_key_steps: [
        "Go to https://fireworks.ai/account/api-keys",
        "Create a new API Key and paste it below",
        "Go to https://fireworks.ai/account/profile",
        "Copy the Account ID, paste it below, and click 'Connect'",
      ],
      featured: false,
      api_key_fields: ["API Key", "Account ID"],
    },
    {
      name: "Amazon Bedrock",
      id: "bedrock",
      description: "So your company has an AWS contract?",
      image: "/images/aws.svg",
      featured: false,
      api_key_steps: [
        "Go to https://us-west-2.console.aws.amazon.com/bedrock/home?region=us-west-2#/overview - be sure to select us-west-2, as it has the most models, and Kiln defaults to this region",
        "Request model access for supported models like Llama and Mistral",
        "Create an IAM Key using this guide https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html and be sure to select 'AmazonBedrockFullAccess' policy when creating the IAM user",
        "Get the access key ID and secret access key for the new user. Paste them below and click 'Connect'",
      ],
      api_key_warning:
        "Bedrock is difficult to setup.\n\nWe suggest OpenRouter as it's easier to setup and has more models.",
      api_key_fields: ["Access Key", "Secret Key"],
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
    bedrock: {
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

  const connect_provider = (provider: Provider) => {
    if (status[provider.id].connected) {
      return
    }
    if (provider.name === "Ollama") {
      connect_ollama()
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
        status.ollama.error = "Failed to connect. Ensure Ollama app is running."
      }
      status.ollama.connected = false
      return
    } finally {
      status.ollama.connecting = false
    }
    if (
      data.supported_models.length === 0 &&
      (!data.untested_models || data.untested_models.length === 0)
    ) {
      status.ollama.error =
        "Ollama running, but no models available. Install some using ollama cli (e.g. 'ollama pull llama3.1')."
      return
    }
    status.ollama.error = null
    status.ollama.connected = true
    const supported_models_str =
      data.supported_models.length > 0
        ? "The following supported models are available: " +
          data.supported_models.join(", ") +
          ". "
        : "No supported models are installed -- we suggest installing some (e.g. 'ollama pull llama3.1'). "
    const untested_models_str =
      data.untested_models && data.untested_models.length > 0
        ? "The following untested models are installed: " +
          data.untested_models.join(", ") +
          ". "
        : ""
    const custom_url_str =
      custom_ollama_url && custom_ollama_url == "http://localhost:11434"
        ? ""
        : "Custom Ollama URL: " + custom_ollama_url
    status.ollama.custom_description =
      "Ollama connected. " +
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
        api_key_issue = true
        return
      }
    }

    api_key_issue = false
    api_key_message = null
    api_key_submitting = true
    try {
      const provider_id = api_key_provider ? api_key_provider.id : ""
      let res = await fetch(
        "http://localhost:8757/api/provider/connect_api_key",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            provider: provider_id,
            key_data: apiKeyData,
          }),
        },
      )
      let data = await res.json()

      if (res.status !== 200) {
        api_key_message =
          data.message || "Failed to connect to provider. Unknown error."
        return
      }

      api_key_issue = false
      api_key_message = null
      status[provider_id].connected = true
      api_key_provider = null
    } catch (e) {
      console.error("submit_api_key error", e)
      api_key_message = "Failed to connect to provider (Exception: " + e + ")"
      api_key_issue = true
      return
    } finally {
      api_key_submitting = false
    }
  }

  let loaded_initial_providers = true
  const check_existing_providers = async () => {
    try {
      let res = await fetch("http://localhost:8757/api/settings")
      let data = await res.json()
      if (data["open_ai_api_key"]) {
        status.openai.connected = true
      }
      if (data["groq_api_key"]) {
        status.groq.connected = true
      }
      if (data["bedrock_access_key"] && data["bedrock_secret_key"]) {
        status.bedrock.connected = true
      }
      if (data["open_router_api_key"]) {
        status.openrouter.connected = true
      }
      if (data["fireworks_api_key"] && data["fireworks_account_id"]) {
        status.fireworks_ai.connected = true
      }
      if (data["ollama_base_url"]) {
        custom_ollama_url = data["ollama_base_url"]
      }
    } catch (e) {
      console.error("check_existing_providers error", e)
    } finally {
      loaded_initial_providers = false
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
</script>

<div class="w-full">
  {#if api_key_provider}
    <div class="grow h-full max-w-[400px] flex flex-col place-content-center">
      <div class="grow"></div>
      {#if api_key_provider.api_key_warning}
        <div role="alert" class="alert alert-warning my-4">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="h-6 w-6 shrink-0 stroke-current"
            fill="none"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          <span>
            <!-- eslint-disable-next-line svelte/no-at-html-tags -->
            {@html api_key_provider.api_key_warning.replace(/\n/g, "<br>")}
          </span>
        </div>
      {/if}

      <h1 class="text-xl font-medium flex-none text-center">
        Connect {api_key_provider.name} with API Key
      </h1>

      <ol class="flex-none my-2 text-gray-700">
        {#each api_key_provider.api_key_steps || [] as step}
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
          {#each api_key_provider.api_key_fields || ["API Key"] as field}
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
            Connect
          {/if}
        </button>
      </div>
      <button
        class="link text-center text-sm mt-8"
        on:click={() => (api_key_provider = null)}
      >
        Cancel setting up {api_key_provider.name}
      </button>
      <div class="grow-[1.5]"></div>
    </div>
  {:else}
    <div class="w-full flex flex-col gap-6 max-w-lg">
      {#each providers as provider}
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
                <div class="badge ml-2 badge-secondary text-xs font-medium">
                  Recommended
                </div>
              {/if}
            </h3>
            {#if status[provider.id] && status[provider.id].error}
              <p class="text-sm text-error" in:fade>
                {status[provider.id].error}
              </p>
            {:else}
              <p class="text-sm text-gray-500">
                {status[provider.id].custom_description || provider.description}
              </p>
            {/if}
            {#if provider.id === "ollama" && status[provider.id] && status[provider.id].error}
              <button
                class="link text-left text-sm text-gray-500"
                on:click={show_custom_ollama_url_dialog}
              >
                Set Custom Ollama URL
              </button>
            {/if}
          </div>
          <button
            class="btn md:min-w-[100px]"
            on:click={() => connect_provider(provider)}
          >
            {#if loaded_initial_providers}
              &nbsp;
            {:else if status[provider.id] && status[provider.id].connected}
              <img
                src="/images/circle-check.svg"
                class="size-6"
                alt="Connected"
              />
            {:else if status[provider.id].connecting}
              <div class="loading loading-spinner loading-md"></div>
            {:else}
              Connect
            {/if}
          </button>
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

    <h3 class="text-lg font-bold">Custom Ollama URL</h3>
    <p class="text-sm font-light mb-8">
      By default, Kiln attempts to connect to Ollama running on localhost:11434.
      If you run Ollama on a custom URL or port, enter it here to connect.
    </p>
    <FormElement
      id="ollama_url"
      label="Ollama URL"
      info_description="It should included the http prefix, and the port number. For example, http://localhost:11434"
      bind:value={custom_ollama_url}
      placeholder="http://localhost:11434"
    />
    <div class="flex flex-row gap-4 items-center mt-4 justify-end">
      <form method="dialog">
        <button class="btn">Cancel</button>
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
        Connect
      </button>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
