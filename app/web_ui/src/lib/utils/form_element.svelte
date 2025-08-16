<script lang="ts">
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import FancySelect from "$lib/ui/fancy_select.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  export let inputType:
    | "input"
    | "textarea"
    | "select"
    | "fancy_select"
    | "multi_select"
    | "header_only"
    | "checkbox" = "input"
  export let id: string
  export let label: string
  export let value: unknown
  export let description: string = ""
  export let info_description: string = ""
  export let placeholder: string | null = null
  export let optional: boolean = false
  export let max_length: number | null = null
  export let error_message: string | null = null // start null because they haven't had a chance to edit it yet
  export let light_label: boolean = false // styling
  export let hide_label: boolean = false
  export let select_options: [unknown, string][] = []
  export let select_options_grouped: [string, [unknown, string][]][] = []
  export let fancy_select_options: OptionGroup[] = []
  export let on_select: (e: Event) => void = () => {}
  export let disabled: boolean = false
  export let info_msg: string | null = null
  export let tall: boolean | "medium" | "xl" = false

  function is_empty(value: unknown): boolean {
    if (value === null || value === undefined) {
      return true
    }
    if (typeof value === "string") {
      return value.length === 0
    }
    return false
  }

  // Export to let parent redefine this. This is a basic "Optional" and max length check
  export let validator: (value: unknown) => string | null = () => {
    if (!optional && is_empty(value)) {
      return '"' + label + '" is required'
    }
    if (max_length && typeof value === "string" && value.length > max_length) {
      return (
        '"' +
        label +
        '" is too long. Max length is ' +
        max_length +
        " characters."
      )
    }
    return null
  }
  // Shorter error message that appears in a badge over the input
  let inline_error: string | null = null
  let initial_run = true
  $: {
    if (initial_run) {
      initial_run = false
    } else if (!optional && is_empty(value)) {
      inline_error = "Required"
    } else if (
      max_length &&
      typeof value === "string" &&
      value.length > max_length
    ) {
      inline_error = "" + value.length + "/" + max_length
    } else {
      inline_error = null
    }
  }

  function run_validator() {
    const error = validator(value)
    error_message = error
  }

  // Little dance to keep type checker happy
  function handleCheckboxChange(event: Event) {
    const target = event.target as HTMLInputElement
    if (target) value = target.checked
  }
</script>

<div>
  <div class="flex flex-row items-center gap-2 pb-[4px]">
    {#if inputType === "checkbox"}
      <input
        type="checkbox"
        {id}
        class="checkbox"
        checked={value ? true : false}
        on:change={handleCheckboxChange}
      />
    {/if}
    <label
      for={id}
      class="text-sm font-medium text-left flex flex-col gap-1 w-full"
    >
      <div class="flex flex-row items-center {hide_label ? 'hidden' : ''}">
        <span class="grow {light_label ? 'text-xs text-gray-500 h-4' : ''}"
          >{label}</span
        >
        <span class="pl-1 text-xs text-gray-500 flex-none"
          >{info_msg || (optional ? "Optional" : "")}</span
        >
        {#if info_description}
          <div class="text-gray-500 {light_label ? 'h-4 mt-[-4px]' : ''}">
            <InfoTooltip tooltip_text={info_description} />
          </div>
        {/if}
      </div>
      {#if description || error_message}
        <div class="text-xs text-gray-500">
          {description || ""}
          {#if error_message}
            <span class="text-error">
              <InfoTooltip tooltip_text={error_message} position="bottom" />
            </span>
          {/if}
        </div>
      {/if}
    </label>
  </div>
  <div class="relative">
    {#if inputType === "textarea"}
      <!-- Ensure compiler doesn't optimize away the heights -->
      <span class="h-18 h-60 hidden"></span>
      <textarea
        placeholder={error_message || placeholder || label}
        {id}
        class="textarea text-base textarea-bordered w-full {tall === true
          ? 'h-60'
          : tall === 'xl'
            ? 'h-96'
            : tall === 'medium'
              ? 'h-36'
              : 'h-18'} wrap-pre text-left align-top
       {error_message || inline_error ? 'textarea-error' : ''}"
        bind:value
        on:input={run_validator}
        autocomplete="off"
        {disabled}
      />
    {:else if inputType === "input"}
      <input
        type="text"
        placeholder={error_message || placeholder || label}
        {id}
        class="input text-base input-bordered w-full font-base {error_message ||
        inline_error
          ? 'input-error'
          : ''}"
        bind:value
        on:input={run_validator}
        autocomplete="off"
        data-op-ignore="true"
        {disabled}
      />
    {:else if inputType === "select"}
      <select
        {id}
        class="select select-bordered w-full {error_message || inline_error
          ? 'select-error'
          : ''}"
        bind:value
        on:input={on_select}
        {disabled}
      >
        {#if select_options_grouped.length > 0}
          {#each select_options_grouped as group}
            <optgroup label={group[0]}>
              {#each group[1] as option}
                <option
                  value={option[0]}
                  disabled={("" + option[0]).startsWith("disabled")}
                  selected={option[0] === value}>{option[1]}</option
                >
              {/each}
            </optgroup>
          {/each}
        {:else}
          {#each select_options as option}
            <option
              value={option[0]}
              disabled={("" + option[0]).startsWith("disabled")}
              selected={option[0] === value}>{option[1]}</option
            >
          {/each}
        {/if}
      </select>
    {:else if inputType === "fancy_select" || inputType === "multi_select"}
      <FancySelect
        bind:options={fancy_select_options}
        bind:selected={value}
        multi_select={inputType === "multi_select"}
      />
    {/if}
    {#if inline_error || (inputType === "select" && error_message)}
      <span
        class="absolute right-3 bottom-4 badge badge-error badge-sm badge-outline text-xs bg-base-100"
      >
        {inline_error || error_message}
      </span>
    {/if}
  </div>
</div>
