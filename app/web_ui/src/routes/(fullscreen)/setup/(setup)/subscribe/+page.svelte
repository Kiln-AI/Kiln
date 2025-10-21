<script lang="ts">
  import { type KilnError, createKilnError } from "$lib/utils/error_handlers"
  import posthog from "posthog-js"
  import Warning from "$lib/ui/warning.svelte"

  let email = ""
  let subscribed = false
  let loading = false
  let error: KilnError | null = null

  async function subscribe() {
    loading = true
    error = null
    try {
      const res = await fetch("https://kiln.tech/api/subscribe_to_newsletter", {
        method: "POST",
        body: JSON.stringify({ email }),
        headers: {
          "Content-Type": "application/json",
        },
      })
      if (res.status !== 200) {
        throw new Error("Failed to subscribe")
      }
      subscribed = true
      posthog.capture("subscribed_to_newsletter")
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  let github_starred = false
  function star_on_github() {
    window.open("https://github.com/kiln-ai/kiln", "_blank")
    github_starred = true
    posthog.capture("github_starred")
  }

  function button_label(subscribed: boolean, github_starred: boolean) {
    if (!subscribed && !github_starred) {
      return "Continue Without Supporting"
    }
    if (!subscribed && github_starred) {
      return "Continue Without Subscribing"
    }
    if (subscribed && !github_starred) {
      return "Continue Without Starring"
    }
    if (subscribed && github_starred) {
      return "Continue"
    }
  }
</script>

<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center">
  Stay in the Loop or Show Your Support
</h1>
<h3 class="text-base font-medium text-center mt-3 max-w-[600px] mx-auto">
  Totally optional
</h3>

<div class="md:w-[400px] max-w-[400px] mx-auto flex flex-col gap-6 mt-8">
  <div
    class="card card-bordered border-base-300 shadow-md hover:shadow-xl transition-all duration-300 group p-4"
  >
    <div class="flex flex-row gap-2 items-center">
      <svg
        class="h-7 group-hover:text-primary transition-all duration-300"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M3 8C3 7.06812 3 6.60218 3.15224 6.23463C3.35523 5.74458 3.74458 5.35523 4.23463 5.15224C4.60218 5 5.06812 5 6 5V5H18V5C18.9319 5 19.3978 5 19.7654 5.15224C20.2554 5.35523 20.6448 5.74458 20.8478 6.23463C21 6.60218 21 7.06812 21 8V16C21 16.9319 21 17.3978 20.8478 17.7654C20.6448 18.2554 20.2554 18.6448 19.7654 18.8478C19.3978 19 18.9319 19 18 19V19H6V19C5.06812 19 4.60218 19 4.23463 18.8478C3.74458 18.6448 3.35523 18.2554 3.15224 17.7654C3 17.3978 3 16.9319 3 16V8Z"
          stroke="currentColor"
          stroke-width="2"
          stroke-linejoin="round"
        />
        <path
          d="M4 6L10.683 11.8476C11.437 12.5074 12.563 12.5074 13.317 11.8476L20 6"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>

      <div class="pl-1">
        <div class="grow text-left text-lg font-medium">
          Subscribe to Newsletter
        </div>
        <div class="text-sm font-light">Zero spam, unsubscribe any time</div>
      </div>
    </div>

    {#if !subscribed}
      <form
        on:submit|preventDefault={subscribe}
        class="flex flex-row gap-2 mt-4 w-full"
      >
        <input
          id="email_input"
          type="email"
          class="input input-bordered w-full"
          placeholder="Email"
          bind:value={email}
          required
        />
        {#if loading}
          <div class="btn btn-disabled min-w-[110px]">
            <div class="loading loading-spinner loading-md"></div>
          </div>
        {:else}
          <button type="submit" class="btn btn-primary min-w-[110px]"
            >Subscribe</button
          >
        {/if}
      </form>
      {#if error}
        <div class="text-sm text-error mt-2 text-center w-full">
          {error.getMessage()}
        </div>
      {/if}
    {:else}
      <div
        class="flex flex-row items-center justify-center font-light mt-4 mb-2 w-full"
      >
        <Warning
          warning_message="Subscribed"
          warning_color="success"
          warning_icon="check"
          tight={true}
        />
      </div>
    {/if}
  </div>

  <button
    class="card card-bordered p-4 border-base-300 shadow-md hover:shadow-xl transition-all duration-300 flex flex-row gap-2 group items-center"
    on:click={star_on_github}
  >
    <svg
      class="ml-[1px] size-7 group-hover:text-primary transition-all duration-300"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M9.15316 5.40838C10.4198 3.13613 11.0531 2 12 2C12.9469 2 13.5802 3.13612 14.8468 5.40837L15.1745 5.99623C15.5345 6.64193 15.7144 6.96479 15.9951 7.17781C16.2757 7.39083 16.6251 7.4699 17.3241 7.62805L17.9605 7.77203C20.4201 8.32856 21.65 8.60682 21.9426 9.54773C22.2352 10.4886 21.3968 11.4691 19.7199 13.4299L19.2861 13.9372C18.8096 14.4944 18.5713 14.773 18.4641 15.1177C18.357 15.4624 18.393 15.8341 18.465 16.5776L18.5306 17.2544C18.7841 19.8706 18.9109 21.1787 18.1449 21.7602C17.3788 22.3417 16.2273 21.8115 13.9243 20.7512L13.3285 20.4768C12.6741 20.1755 12.3469 20.0248 12 20.0248C11.6531 20.0248 11.3259 20.1755 10.6715 20.4768L10.0757 20.7512C7.77268 21.8115 6.62118 22.3417 5.85515 21.7602C5.08912 21.1787 5.21588 19.8706 5.4694 17.2544L5.53498 16.5776C5.60703 15.8341 5.64305 15.4624 5.53586 15.1177C5.42868 14.773 5.19043 14.4944 4.71392 13.9372L4.2801 13.4299C2.60325 11.4691 1.76482 10.4886 2.05742 9.54773C2.35002 8.60682 3.57986 8.32856 6.03954 7.77203L6.67589 7.62805C7.37485 7.4699 7.72433 7.39083 8.00494 7.17781C8.28555 6.96479 8.46553 6.64194 8.82547 5.99623L9.15316 5.40838Z"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      />
    </svg>
    <div class="grow text-left pl-1 text-lg font-medium">Star us on GitHub</div>
  </button>
</div>

<div
  class="flex-none flex flex-col place-content-center md:flex-row gap-4 mt-12"
>
  <a href="/setup/connect_providers">
    <button
      class="btn {subscribed && github_starred
        ? 'btn-primary'
        : ''} w-full min-w-[130px]"
    >
      {button_label(subscribed, github_starred)}
    </button></a
  >
</div>
