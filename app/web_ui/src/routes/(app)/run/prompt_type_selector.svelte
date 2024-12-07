<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"

  export let prompt_method: string
  export let exclude_cot = false
  export let show_custom = false
  export let description: string | undefined = undefined
  export let info_description: string | undefined = undefined
  $: options = build_prompt_options(exclude_cot, show_custom)

  function build_prompt_options(exclude_cot: boolean, show_custom: boolean) {
    const prompt_options: [string, string][] = [
      ["basic", "Basic Prompt (Zero Shot)"],
      ["few_shot", "Few Shot"],
      ["many_shot", "Many Shot"],
      ["repairs", "Repair Multi Shot"],
    ]

    if (!exclude_cot) {
      prompt_options.push(
        ["simple_chain_of_thought", "Basic Chain of Thought"],
        ["few_shot_chain_of_thought", "Chain of Thought - Few Shot"],
        ["multi_shot_chain_of_thought", "Chain of Thought - Many Shot"],
      )
    }

    if (show_custom) {
      prompt_options.push(["custom", "Custom Prompt"])
    }

    return prompt_options
  }
</script>

<FormElement
  label="Prompt Method"
  inputType="select"
  {description}
  {info_description}
  bind:value={prompt_method}
  id="prompt_method"
  select_options={options}
/>
