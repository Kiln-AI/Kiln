<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { type KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import { setup_ph_user } from "$lib/utils/connect_ph"
  import {
    redirect_to_work,
    redirect_after_registration,
  } from "../registration_helpers"

  let email = ""
  let full_name = ""
  let loading = false
  let error: KilnError | null = null

  async function switch_to_work() {
    loading = true
    error = null
    try {
      const { error: settings_error } = await client.POST("/api/settings", {
        body: {
          user_type: "work",
          personal_use_contact: null,
        },
      })
      if (settings_error) {
        throw settings_error
      }
      redirect_to_work()
    } catch (e) {
      console.error("Error switching to work", e)
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  async function register() {
    loading = true
    error = null
    try {
      if (!full_name) {
        throw new Error("Full name is required")
      }
      const { error } = await client.POST("/api/settings", {
        body: {
          user_type: "personal",
          personal_use_contact: email,
        },
      })
      if (error) {
        throw error
      }
      const res = await fetch("https://kiln.tech/api/subscribe_to_newsletter", {
        method: "POST",
        body: JSON.stringify({
          email,
          work_use: "false",
          full_name,
        }),
        headers: {
          "Content-Type": "application/json",
        },
      })
      if (res.status !== 200) {
        throw new Error("Failed to register")
      }

      // No need to await this
      setup_ph_user()

      redirect_after_registration()
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }
</script>

<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center">
  Register for Personal Use
</h1>
<h3
  class="text-base font-medium text-center mt-3 max-w-[600px] mx-auto text-balance"
>
  Non-commercial use only.
</h3>

<div
  class="flex-none py-4 h-full flex flex-col w-full mx-auto items-center justify-center"
>
  <div class="max-w-[280px] mx-auto mt-2">
    <FormContainer
      on:submit={register}
      submit_label="Continue"
      keyboard_submit={false}
      submitting={loading}
      {error}
    >
      <FormElement
        id="full_name"
        inputType="input"
        label="Full Name"
        bind:value={full_name}
      />
      <FormElement
        id="email"
        inputType="input"
        label="Work Email"
        bind:value={email}
      />
    </FormContainer>
  </div>
</div>

<div class="text-center font-light mt-4">
  Or <button class="link" on:click={switch_to_work}
    >switch to commercial use (free!)</button
  >
</div>
