<script lang="ts">
  import CheckmarkListIcon from "./checkmark_list_icon.svelte"
  import { goto } from "$app/navigation"
  import { onMount } from "svelte"
  import { type KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"

  async function selectAccountType(type: "personal" | "work") {
    try {
      // Save the selected account type
      const { error } = await client.POST("/api/settings", {
        body: {
          user_type: type,
        },
      })
      if (error) {
        throw error
      }

      if (type === "personal") {
        goto("/setup/subscribe")
      } else {
        goto("/setup/register_work")
      }
    } catch (error) {
      console.error("Error selecting account type", error)
      settings_error = createKilnError(error)
    }
  }

  onMount(() => {
    load_settings()
  })

  let loading = true
  let settings_error: KilnError | null = null
  async function load_settings() {
    loading = true
    settings_error = null
    try {
      const { data, error } = await client.GET("/api/settings")
      if (error) {
        throw error
      }
      const user_type = data.user_type
      const work_use_contact = data.work_use_contact

      // Check if they have already selected an account type
      if (user_type === "personal") {
        goto("/setup/connect_providers", { replaceState: true })
      } else if (user_type === "work") {
        if (!work_use_contact) {
          goto("/setup/register_work", { replaceState: true })
        } else {
          goto("/setup/connect_providers", { replaceState: true })
        }
      }
    } catch (error) {
      console.error("Error loading settings", error)
      settings_error = createKilnError(error)
    } finally {
      loading = false
    }
  }
</script>

<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center mb-6 md:mb-12">
  How do you want to use Kiln?
</h1>

{#if loading}
  <div class="flex-none flex justify-center">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
{:else if settings_error}
  <div class="flex-none w-full max-w-5xl px-4">
    <div class="flex flex-col justify-center items-center gap-2">
      <div class="text-error">Error: Ensure Kiln is Running</div>
      <div class="text-sm text-gray-500">
        {settings_error.getMessage()}
      </div>
      <button
        class="btn btn-ghose btn-sm mt-4"
        on:click={() => window.location.reload()}>Reload</button
      >
    </div>
  </div>
{:else}
  <div class="flex-none w-full max-w-5xl px-4">
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
      <button
        class="card card-bordered border-base-300 shadow-md hover:shadow-xl hover:border-primary hover:-translate-y-1 hover:scale-[1.02] transition-all duration-300 cursor-pointer p-6 text-left"
        on:click={() => selectAccountType("personal")}
      >
        <h2 class="text-2xl font-medium mb-4">Personal</h2>
        <ul class="space-y-3 mb-6 flex-grow">
          <li class="flex items-start">
            <CheckmarkListIcon />
            <span>Free</span>
          </li>
          <li class="flex items-start">
            <CheckmarkListIcon />
            <span>No Signup Required</span>
          </li>
          <li class="flex items-start">
            <CheckmarkListIcon />
            <div>
              <div>For Personal Use</div>
              <div class="text-sm text-gray-500">
                Not licensed for commercial use
              </div>
            </div>
          </li>
        </ul>
        <div class="btn btn-outline btn-primary w-full pointer-events-none">
          Start Personal
        </div>
      </button>

      <button
        class="card card-bordered border-base-300 shadow-md hover:shadow-xl hover:border-primary hover:-translate-y-1 hover:scale-[1.02] transition-all duration-300 cursor-pointer p-6 text-left"
        on:click={() => selectAccountType("work")}
      >
        <h2 class="text-2xl font-medium mb-4">For Work</h2>
        <ul class="space-y-3 mb-6 flex-grow">
          <li class="flex items-start">
            <CheckmarkListIcon />
            <span>Free</span>
          </li>
          <li class="flex items-start">
            <CheckmarkListIcon />
            <div>
              <div>Work Email Required</div>
              <div class="text-sm text-gray-500">Only takes 10 seconds</div>
            </div>
          </li>
          <li class="flex items-start">
            <CheckmarkListIcon />
            <span>For Work and Enterprise Projects</span>
          </li>
        </ul>
        <div class="btn btn-outline btn-primary w-full pointer-events-none">
          Start Work
        </div>
      </button>
    </div>
  </div>
{/if}
