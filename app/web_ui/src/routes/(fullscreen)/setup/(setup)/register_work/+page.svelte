<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { type KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Warning from "$lib/ui/warning.svelte"
  import { goto } from "$app/navigation"
  import { registration_state } from "$lib/stores/registration_store"

  let email = ""
  let allow_personal_email_domains = false
  let entered_personal_email = false
  let loading = false
  let error: KilnError | null = null

  async function switch_to_personal() {
    registration_state.update((state) => ({
      ...state,
      selected_account_type: "personal",
    }))
    goto("/setup/connect_providers")
  }

  async function register() {
    loading = true
    error = null
    try {
      if (!allow_personal_email_domains && check_personal_email_domain(email)) {
        entered_personal_email = true
        return
      }
      registration_state.update((state) => ({
        ...state,
        work_email: email,
      }))
      const res = await fetch(
        "https://kiln.tech/api/subscribe_to_newsletter?work_use=true",
        {
          method: "POST",
          body: JSON.stringify({ email }),
          headers: {
            "Content-Type": "application/json",
          },
        },
      )
      if (res.status !== 200) {
        throw new Error("Failed to register")
      }

      goto("/setup/connect_providers")
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  function check_personal_email_domain(email: string): boolean {
    return (
      email.includes("@gmail.com") ||
      email.includes("@yahoo.com") ||
      email.includes("@hotmail.com") ||
      email.includes("@outlook.com") ||
      email.includes("@icloud.com") ||
      email.includes("@aol.com") ||
      email.includes("@verizon.net") ||
      email.includes("@comcast.net") ||
      email.includes("@sbcglobal.net") ||
      email.includes("@att.net") ||
      email.includes("@yahoo.co.uk") ||
      email.includes("@yahoo.com.au") ||
      email.includes("@qq.com") ||
      email.includes("@163.com") ||
      email.includes("@126.com") ||
      email.includes("@yeah.net") ||
      email.includes("@sina.com")
    )
  }
</script>

<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center">
  Register for Work Use
</h1>
<h3
  class="text-base font-medium text-center mt-3 max-w-[600px] mx-auto text-balance"
>
  Kiln is currently free to use at work — just register with your work email to
  unlock commercial use.
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
        id="email"
        inputType="input"
        label="Work Email"
        bind:value={email}
      />
      {#if entered_personal_email}
        <div>
          <FormElement
            id="allow_personal_email_domains"
            inputType="checkbox"
            label="This is my work email address"
            bind:value={allow_personal_email_domains}
          />
          <Warning
            warning_message="This looks like a personal email address. You must attest this is your primary work email address to unlock commercial usage."
          />
        </div>
      {/if}
    </FormContainer>
  </div>
</div>

<div class="text-center font-light mt-4">
  Or <button class="link" on:click={switch_to_personal}
    >switch to personal non-commercial use</button
  >.
</div>
