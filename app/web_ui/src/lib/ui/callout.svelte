<script lang="ts">
  // Reusable callout card — primary-colored bordered/tinted box with an icon
  // bubble, title, description, and an optional action button. Modeled after
  // the "Update Available" banner in /settings.
  //
  // The action button is optional. Provide either `button_href` (renders an
  // <a>) or `button_onclick` (renders a <button>) along with `button_label`
  // to show it. The icon is supplied via the `icon` slot.
  export let title: string
  export let description: string
  export let button_label: string | null = null
  export let button_href: string | null = null
  export let button_onclick: (() => void) | null = null
  export let testid: string | null = null
</script>

<div
  class="card card-bordered border-primary/30 bg-primary/5 shadow-sm rounded-md"
  data-testid={testid}
>
  <div class="flex flex-row items-start sm:items-center gap-4 p-4">
    <div
      class="flex-shrink-0 w-9 h-9 rounded-full bg-primary/10 text-primary flex items-center justify-center"
    >
      <div class="w-5 h-5">
        <slot name="icon" />
      </div>
    </div>
    <div
      class="flex-grow min-w-0 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4"
    >
      <div class="flex-grow min-w-0">
        <div class="font-medium text-primary">{title}</div>
        <div class="text-sm font-light text-gray-500">{description}</div>
      </div>
      {#if button_label}
        {#if button_href}
          <a
            href={button_href}
            class="btn btn-primary btn-sm flex-shrink-0 self-start sm:self-auto"
          >
            {button_label}
          </a>
        {:else if button_onclick}
          <button
            type="button"
            class="btn btn-primary btn-sm flex-shrink-0 self-start sm:self-auto"
            on:click={button_onclick}
          >
            {button_label}
          </button>
        {/if}
      {/if}
    </div>
  </div>
</div>
