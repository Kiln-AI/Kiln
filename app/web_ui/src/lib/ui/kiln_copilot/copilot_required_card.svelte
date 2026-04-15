<script lang="ts">
  import Intro from "../intro.svelte"

  export let title: string = "Kiln Copilot Required"
  export let description_markdown: string
  export let auth_href: string
  export let learn_more_label: string | null = null
  export let learn_more_href: string | null = null
  export let compact: boolean = false
  export let connect_button_label: string = "Connect Kiln Copilot"
  export let icon: "logo" | "chat" = "logo"
</script>

<div
  class="flex flex-col items-center justify-center {compact
    ? 'flex-1 min-h-0 min-w-0 overflow-y-auto py-3'
    : 'min-h-[60vh]'}"
>
  <Intro
    {title}
    {description_markdown}
    action_buttons={[
      {
        label: connect_button_label,
        href: auth_href,
        is_primary: true,
      },
      ...(learn_more_label && learn_more_href
        ? [
            {
              label: learn_more_label,
              href: learn_more_href,
              is_primary: false,
              new_tab: true,
            },
          ]
        : []),
    ]}
  >
    <div slot="icon">
      {#if icon === "logo"}
        <div class="h-12 w-12">
          <img src="/images/animated_logo.svg" alt="Kiln logo" />
        </div>
      {:else if icon === "chat"}
        <div class="w-16">
          <img src="/images/chat_icon.svg" alt="Kiln chat icon" />
        </div>
      {/if}
    </div>
  </Intro>
</div>
