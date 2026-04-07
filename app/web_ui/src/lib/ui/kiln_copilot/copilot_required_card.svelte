<script lang="ts">
  import Intro from "../intro.svelte"

  export let description_markdown: string
  export let auth_href: string
  export let learn_more_label: string
  export let learn_more_href: string
  export let compact: boolean = false
</script>

<div
  class="flex flex-col items-center justify-center {compact
    ? 'flex-1 min-h-0 min-w-0 overflow-y-auto py-3'
    : 'min-h-[60vh]'}"
>
  <Intro
    title="Kiln Copilot Required"
    {description_markdown}
    action_buttons={[
      {
        label: "Connect Kiln Copilot",
        href: auth_href,
        is_primary: true,
      },
      {
        label: learn_more_label,
        href: learn_more_href,
        is_primary: false,
        new_tab: true,
      },
    ]}
  >
    <div slot="icon">
      <div class="h-12 w-12">
        <img src="/images/animated_logo.svg" alt="Kiln Copilot" />
      </div>
    </div>
  </Intro>
</div>
