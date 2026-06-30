<script lang="ts">
  import type {
    InlineAction,
    RadioOption,
  } from "$lib/utils/form_element.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  export let id: string = ""
  export let label: string = ""
  export let value: unknown = ""
  export let description: string = ""
  export let inputType: string = "input"
  export let optional: boolean = false
  export let select_options: unknown[] = []
  export let fancy_select_options: OptionGroup[] = []
  export let error_message: string | null = null
  export let info_description: string = ""
  export let on_select: (e: Event) => void = () => {}
  export let disabled: boolean = false
  export let min: number | null = null
  export let max: number | null = null
  export let placeholder: string | null = null
  export let hide_optional_badge: boolean = false
  export let hide_label: boolean = false
  export let aria_label: string | null = null
  export let inline_action: InlineAction | null = null
  export let radio_options: RadioOption[] = []
  export let on_radio_change: (() => void) | null = null

  export let validator: (value: unknown) => string | null = () => null
  export function run_validator() {
    error_message = validator(value)
  }
</script>

<div
  data-testid="form-element-{id}"
  data-label={label}
  data-type={inputType}
  data-description={description}
  data-info-description={info_description}
  data-inline-action-label={inline_action?.label || ""}
  data-hide-label={hide_label ? "true" : "false"}
  data-placeholder={placeholder || ""}
>
  {#if inputType === "radio"}
    <div data-testid="radio-group-{id}">
      {#each radio_options as option}
        <label>
          <input
            type="radio"
            name={id}
            value={option.value}
            checked={value === option.value}
            on:change={() => {
              value = option.value
              if (on_radio_change) on_radio_change()
            }}
          />
          <span>{option.label}</span>
          {#if option.description}
            <span>{option.description}</span>
          {/if}
        </label>
      {/each}
    </div>
  {:else if inputType === "input"}
    <input type="text" data-testid="input-{id}" {placeholder} bind:value />
  {:else if inputType === "fancy_select"}
    <div data-testid="fancy-select-{id}">
      {#each fancy_select_options as group}
        {#each group.options as option}
          <button
            type="button"
            data-testid="fancy-option-{option.value}"
            data-value={option.value}
            class:selected={value === option.value}
            on:click={() => {
              value = option.value
            }}
          >
            <span>{option.label}</span>
            {#if option.description}
              <span class="description">{option.description}</span>
            {/if}
          </button>
        {/each}
      {/each}
    </div>
  {/if}
  {#if inline_action}
    <button
      type="button"
      data-testid="inline-action-{id}"
      on:click={inline_action.handler}
    >
      {inline_action.label}
    </button>
  {/if}
  <slot />
</div>
