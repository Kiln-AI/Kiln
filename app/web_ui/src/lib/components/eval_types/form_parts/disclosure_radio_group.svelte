<script context="module" lang="ts">
  export type RadioOption = {
    value: string
    label: string
    description?: string
  }
</script>

<script lang="ts">
  import { createEventDispatcher } from "svelte"

  export let name: string
  export let options: RadioOption[]
  export let selected: string

  const dispatch = createEventDispatcher<{ change: string }>()
</script>

<div
  role="radiogroup"
  aria-label={name}
  class="flex flex-col gap-2"
  data-testid="disclosure-radio-group-{name}"
>
  {#each options as option}
    <label
      class="flex items-start gap-2.5 cursor-pointer rounded-lg border px-3 py-2.5 transition-colors
        {selected === option.value
        ? 'border-primary/30 bg-primary/[0.03]'
        : 'border-base-300 hover:border-base-content/20'}"
    >
      <input
        type="radio"
        {name}
        class="radio radio-sm radio-primary mt-0.5 flex-none"
        value={option.value}
        bind:group={selected}
        on:change={() => dispatch("change", option.value)}
      />
      <span class="flex flex-col gap-0.5">
        <span class="text-sm font-medium">{option.label}</span>
        {#if option.description}
          <span class="text-xs text-base-content/60">{option.description}</span>
        {/if}
      </span>
    </label>
  {/each}
</div>
