<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { type KilnError, createKilnError } from "$lib/utils/error_handlers"

  let email = ""
  let subscribed = false
  let loading = false
  let error: KilnError | null = null

  async function subscribe() {
    loading = true
    error = null
    try {
      console.log("Subscribing to newsletter local to remote", email)
      const res = await fetch(
        "https://getkiln.ai/api/subscribe_to_newsletter",
        {
          method: "POST",
          body: JSON.stringify({ email }),
          headers: {
            "Content-Type": "application/json",
          },
        },
      )
      if (res.status !== 200) {
        throw new Error("Failed to subscribe")
      }
      subscribed = true
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }
</script>

<div class="grow"></div>
<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center">Newsletter</h1>
<h3 class="text-base font-medium text-center mt-3 max-w-[600px] mx-auto">
  Zero spam, unsubscribe any time, totally optional.
</h3>

<div
  class="flex-none min-h-[50vh] py-8 h-full flex flex-col py-18 w-full mx-auto items-center justify-center"
>
  {#if !subscribed}
    <h3
      class="text-base mb-5 font-light text-center mt-3 max-w-[420px] mx-auto"
    >
      Subscribe to our newsletter to learn about new features, updates, new
      models, and other Kiln AI news.
    </h3>
    <div class="max-w-[280px] mx-auto">
      <FormContainer
        on:submit={subscribe}
        submit_label="Subscribe"
        keyboard_submit={false}
        submitting={loading}
        {error}
      >
        <FormElement
          id="email"
          inputType="input"
          label="Email"
          bind:value={email}
        />
      </FormContainer>
    </div>
  {:else}
    <div
      class="text-center text-lg font-medium text-success flex flex-row items-center justify-center gap-2 mb-2"
    >
      <svg
        fill="currentColor"
        class="size-6"
        viewBox="0 0 512 512"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M256,48C141.31,48,48,141.31,48,256s93.31,208,208,208,208-93.31,208-208S370.69,48,256,48ZM364.25,186.29l-134.4,160a16,16,0,0,1-12,5.71h-.27a16,16,0,0,1-11.89-5.3l-57.6-64a16,16,0,1,1,23.78-21.4l45.29,50.32L339.75,165.71a16,16,0,0,1,24.5,20.58Z"
        />
      </svg>
      Subscribed!
    </div>
    <p class="text-center">Thanks for subscribing! ❤️</p>
  {/if}
</div>

<div class="flex-none flex flex-col place-content-center md:flex-row gap-4">
  <a href="/setup/connect_providers">
    <button class="btn {subscribed ? 'btn-primary' : ''} w-full min-w-[130px]">
      Continue {subscribed ? "" : " Without Subscribing"}
    </button></a
  >
</div>
