<script lang="ts">
  import CheckmarkListIcon from "./checkmark_list_icon.svelte"
  import { registration_state } from "$lib/stores/registration_store"
  import { goto } from "$app/navigation"
  import { onMount } from "svelte"

  function selectAccountType(type: "personal" | "work") {
    registration_state.update((state) => ({
      ...state,
      selected_account_type: type,
    }))

    if (type === "personal") {
      goto("/setup/subscribe")
    } else {
      goto("/setup/register_work")
    }
  }

  onMount(async () => {
    // Check if they have already selected an account type
    if ($registration_state.selected_account_type === "personal") {
      goto("/setup/connect_providers", { replaceState: true })
    } else if ($registration_state.selected_account_type === "work") {
      if ($registration_state.work_email === null) {
        goto("/setup/register_work", { replaceState: true })
      } else {
        goto("/setup/connect_providers", { replaceState: true })
      }
    }
  })
</script>

<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center mb-6 md:mb-12">
  How do you want to use Kiln?
</h1>

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
