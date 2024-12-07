<script lang="ts">
  export let inputType: "input" | "textarea" | "select" = "input"
  export let id: string
  export let label: string
  export let value: unknown
  export let description: string = ""
  export let info_description: string = ""
  export let optional: boolean = false
  export let max_length: number | null = null
  export let error_message: string | null = null // start null because they haven't had a chance to edit it yet
  export let light_label: boolean = false // styling
  export let select_options: [unknown, string][] = []
  export let select_options_grouped: [string, [unknown, string][]][] = []
  export let disabled: boolean = false
  export let info_msg: string | null = null

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
</script>

<div>
  <label
    for={id}
    class="text-sm font-medium text-left flex flex-col gap-1 pb-[4px]"
  >
    <div class="flex flex-row items-center">
      <span class="grow {light_label ? 'text-xs text-gray-500' : ''}"
        >{label}</span
      >
      <span class="pl-1 text-xs text-gray-500 flex-none"
        >{info_msg || (optional ? "Optional" : "")}</span
      >
      {#if info_description}
        <div>
          <button class="tooltip tooltip-left" data-tip={info_description}>
            <svg
              fill="currentColor"
              class="w-6 h-6 inline"
              viewBox="0 0 1024 1024"
              version="1"
              xmlns="http://www.w3.org/2000/svg"
              ><path
                d="M512 717a205 205 0 1 0 0-410 205 205 0 0 0 0 410zm0 51a256 256 0 1 1 0-512 256 256 0 0 1 0 512z"
              /><path
                d="M485 364c7-7 16-11 27-11s20 4 27 11c8 8 11 17 11 28 0 10-3 19-11 27-7 7-16 11-27 11s-20-4-27-11c-8-8-11-17-11-27 0-11 3-20 11-28zM479 469h66v192h-66z"
              /></svg
            >
          </button>
        </div>
      {/if}
    </div>
    {#if description}
      <div class="text-xs text-gray-500">
        {description}
      </div>
    {/if}
  </label>
  <div class="relative">
    {#if inputType === "textarea"}
      <textarea
        placeholder={error_message || label}
        {id}
        class="textarea text-base textarea-bordered w-full h-18 wrap-pre text-left align-top
       {error_message || inline_error ? 'textarea-error' : ''}"
        bind:value
        on:input={run_validator}
        autocomplete="off"
        {disabled}
      />
    {:else if inputType === "input"}
      <input
        type="text"
        placeholder={error_message || label}
        {id}
        class="input text-base input-bordered w-full font-base {error_message ||
        inline_error
          ? 'input-error'
          : ''}"
        bind:value
        on:input={run_validator}
        autocomplete="off"
        {disabled}
      />
    {:else if inputType === "select"}
      <select
        {id}
        class="select select-bordered w-full {error_message || inline_error
          ? 'select-error'
          : ''}"
        bind:value
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
