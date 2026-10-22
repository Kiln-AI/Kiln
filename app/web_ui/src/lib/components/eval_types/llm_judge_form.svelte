<script lang="ts">
  import type { AvailableModels } from "$lib/types"
  import AvailableModelsDropdown from "$lib/ui/run_config_component/available_models_dropdown.svelte"
  import { build_suggested_models } from "$lib/ui/run_config_component/suggested_models"
  import { get_provider_image } from "$lib/ui/provider_image"
  import { available_models } from "$lib/stores"
  import Collapse from "$lib/ui/collapse.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import type { RadioOption } from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import JudgePromptFields from "$lib/components/eval_types/judge_prompt_fields.svelte"
  import {
    getDefaultLlmJudgePrompt,
    type DefaultLlmJudgePromptResponse,
  } from "$lib/api/v2_eval_api"
  import {
    judge_algorithm_for_model,
    unsupported_judge_algorithms,
    type JudgeAlgorithm,
  } from "$lib/utils/eval_types/judge_algorithm"
  import { createEventDispatcher, onMount } from "svelte"

  export let task_id: string
  export let project_id: string
  export let eval_id: string

  export let model_name: string | undefined = undefined
  export let provider_name: string | undefined = undefined
  export let combined_model_name: string | undefined = undefined
  export let selected_algo: JudgeAlgorithm | undefined = undefined

  export let judge_prompt: string | undefined = undefined
  export let system_prompt: string | undefined = undefined

  // Evals with no spec or template have no data to derive judging steps from;
  // the user writes them here instead. The steps are stored on the judge
  // config and bound to {{ judge_instructions }} in the prompt template, so
  // there's nothing to keep in sync between the two editing surfaces.
  // The server decides which evals these are: its default prompt references
  // {{ judge_instructions }} exactly when steps can't be derived, so keying
  // the UI off the fetched default can never drift from the backend logic.
  export let judge_instructions: string[] = []
  let show_instructions_ui = false

  // FormList keys its rows by item value, so a plain string[] breaks the
  // moment two rows are empty (duplicate keys). Wrap each step in an object
  // (unique by identity) and derive the exported string[] from it.
  let instruction_items: { value: string }[] = [{ value: "" }]
  $: judge_instructions = instruction_items.map((item) => item.value)

  const instruction_placeholders = [
    'e.g. "Does the model\'s output contain the issue X?"',
    'e.g. "Is the model\'s output missing any required information?"',
    'e.g. "Considering the above, should the output pass or fail?"',
  ]

  let prompt_fetch_error: string | null = null

  /**
   * The reference data keys the server will require of this judge, and whether they
   * could be fetched at all. Bound out so the Test Judge pane can offer a place to
   * supply them: the server derives the requirement from the eval, not from the prompt
   * text, so editing the reference block out of the prompt does not remove it.
   *
   * `default_prompt_unavailable` tracks the outcome of each fetch attempt, not just
   * its failures — see the clear in `load_default_prompt`. The pane fails open on
   * "unknown", so a value left set from a previous attempt would keep offering an
   * input nothing needs.
   */
  export let default_reference_keys: string[] = []
  export let default_prompt_unavailable: boolean = false

  // Agentic judges have their own default prompt, so it is refetched whenever the
  // selection moves to or from Agentic Judge. A prompt field still holding the last
  // fetched default takes the new one; a field the user edited is kept.
  let requested_trace_tools: boolean | null = null
  let last_default: DefaultLlmJudgePromptResponse | null = null
  let latest_request_id = 0

  // Fired when a fetch changes a prompt the user may already have tested, since the
  // change arrives without the DOM input events the builder watches for edits.
  const dispatch = createEventDispatcher<{ prompt_replaced: void }>()

  onMount(() => load_default_prompt(wants_trace_tools))

  async function load_default_prompt(trace_tools: boolean) {
    requested_trace_tools = trace_tools
    const request_id = ++latest_request_id
    let defaults: DefaultLlmJudgePromptResponse | null = null
    try {
      // Cleared up front, not left to the initializer: `bind:` seeds this child from
      // the parent's retained value, so a form recreated after one failed fetch starts
      // at `true` and would stay there for the session.
      default_prompt_unavailable = false
      defaults = await getDefaultLlmJudgePrompt(
        project_id,
        task_id,
        eval_id,
        trace_tools,
      )
    } catch (e) {
      console.warn("Failed to fetch default LLM judge prompt:", e)
    }
    if (request_id !== latest_request_id) return

    if (defaults) {
      prompt_fetch_error = null
      show_instructions_ui = defaults.judge_prompt.includes(
        "{{ judge_instructions }}",
      )
      default_reference_keys = defaults.reference_keys ?? []
    } else {
      prompt_fetch_error =
        "Could not load default judge prompt. The server will use its default."
      default_prompt_unavailable = true
    }
    replace_unedited_prompts(defaults)
  }

  // With no new default, an unedited field is cleared rather than left holding the
  // other algorithm's default. A test then sends no prompt and the server builds the
  // default; the required Judge Prompt field blocks Save until the user writes one.
  function replace_unedited_prompts(
    defaults: DefaultLlmJudgePromptResponse | null,
  ) {
    const previous_judge_prompt = judge_prompt
    const previous_system_prompt = system_prompt
    if (judge_prompt === last_default?.judge_prompt) {
      judge_prompt = defaults?.judge_prompt
    }
    if (system_prompt === last_default?.system_prompt) {
      system_prompt = defaults?.system_prompt
    }
    last_default = defaults

    const replaced = (
      previous: string | undefined,
      current: string | undefined,
    ) => previous !== undefined && previous !== current
    if (
      replaced(previous_judge_prompt, judge_prompt) ||
      replaced(previous_system_prompt, system_prompt)
    ) {
      dispatch("prompt_replaced")
    }
  }

  const evaluator_algorithms: (RadioOption & { value: JudgeAlgorithm })[] = [
    {
      value: "llm_as_judge",
      label: "LLM as Judge",
      description:
        "The model selected above will be asked to judge task outputs.",
    },
    {
      value: "g_eval",
      label: "G-Eval Judge",
      description:
        "A more advanced LLM-as-Judge method which considers token probabilities for more precise scores.",
    },
    {
      value: "agentic_judge",
      label: "Agentic Judge",
      description:
        "Reads the trace with tools, only the parts it needs. Best for long agent traces.",
    },
  ]

  $: suggested_models = build_suggested_models($available_models || [], "evals")
  let force_select_dropdown = false

  // The algorithm the user picked. Only a pick survives a model change; an
  // automatic default is recomputed for each model.
  let chosen_algo: JudgeAlgorithm | undefined = undefined

  $: unsupported_algos = update_unsupported_algos_and_selected_algo(
    $available_models,
    model_name,
    provider_name,
  )
  function update_unsupported_algos_and_selected_algo(
    avail_models: AvailableModels[],
    mn: string | undefined,
    pn: string | undefined,
  ): Partial<Record<JudgeAlgorithm, string>> {
    const model_info = avail_models
      .find((m) => m.provider_id === pn)
      ?.models.find((m) => m.id === mn)
    if (!model_info) {
      selected_algo = undefined
      return {}
    }
    selected_algo = judge_algorithm_for_model(chosen_algo, model_info)
    if (selected_algo !== chosen_algo) {
      chosen_algo = undefined
    }
    return unsupported_judge_algorithms(model_info)
  }

  // Must stay below the model-change block above: Svelte orders reactive blocks by
  // the variables they name, and that block sets selected_algo inside a function.
  $: wants_trace_tools = selected_algo === "agentic_judge"
  $: if (
    requested_trace_tools !== null &&
    wants_trace_tools !== requested_trace_tools
  ) {
    load_default_prompt(wants_trace_tools)
  }

  $: available_algorithms = evaluator_algorithms.filter(
    (algo) => !unsupported_algos[algo.value],
  )
  $: show_algorithm_section = model_name && available_algorithms.length > 1

  // Runs after the radio's bind:value has already updated selected_algo.
  function remember_chosen_algo() {
    chosen_algo = selected_algo
  }
</script>

<div class="flex flex-col gap-6">
  <div class="text-sm font-medium text-left flex flex-col gap-1">
    <div class="text-xl font-bold">Select Judge Model</div>
    <div class="text-xs text-gray-500">
      Specify which model will be used for the judge. This is not necessarily
      the model that will be used to run the task.
    </div>
  </div>

  {#if !model_name && !force_select_dropdown && suggested_models.length > 0}
    <div>
      <div class="font-light text-lg text-gray-500 mb-2">
        Recommended Models:
      </div>
      <div class="flex flex-wrap flex-row gap-4">
        {#each suggested_models as model}
          {@const provider_image = get_provider_image(model.provider_id)}
          <button
            class="card card-bordered border-base-300 shadow-md hover:shadow-lg hover:border-primary/50 transition-all duration-200 w-[120px] min-h-[120px] p-3 flex flex-col justify-center items-center text-center group cursor-pointer"
            on:click={() => {
              model_name = model.model_name
              provider_name = model.provider_name
              combined_model_name = `${model.provider_id}/${model.model_id}`
            }}
          >
            <div class="flex flex-col gap-2 items-center">
              <img
                src={provider_image}
                class="w-6 h-6"
                alt={model.provider_name}
              />
              <div class="flex flex-col gap-1">
                <div class="font-medium text-sm leading-tight">
                  {model.model_name}
                </div>
                <div class="text-xs text-gray-500">
                  {model.provider_name}
                </div>
              </div>
            </div>
          </button>
        {/each}
      </div>
      <div class="font-light text-lg text-gray-500 mt-8 mb-2">
        Other Available Models:
      </div>
      <div class="flex flex-row gap-2">
        <button
          class="btn btn-outline btn-wide"
          on:click={() => (force_select_dropdown = true)}
        >
          Browse All Models
        </button>
      </div>
    </div>
  {:else}
    <AvailableModelsDropdown
      {task_id}
      bind:model={combined_model_name}
      bind:model_name
      bind:provider_name
      settings={{
        requires_structured_output: selected_algo !== "g_eval",
        requires_logprobs: selected_algo === "g_eval",
        requires_tool_support: selected_algo === "agentic_judge",
        suggested_mode: "evals",
      }}
    />
  {/if}

  {#if show_algorithm_section}
    <div data-testid="algorithm-section">
      <div class="text-xl font-bold mb-2">Select Judge Algorithm</div>
      <!-- Not required here: the builder shows Save only once an algorithm is selected. -->
      <FormElement
        id="judge_algorithm"
        aria_label="Judge Algorithm"
        inputType="radio"
        radio_options={available_algorithms}
        optional={true}
        bind:value={selected_algo}
        on_radio_change={remember_chosen_algo}
      />
    </div>
  {/if}

  {#if show_instructions_ui}
    <div class="text-sm font-medium text-left flex flex-col gap-1">
      <div class="text-xl font-bold">Evaluation Instructions</div>
      <div class="text-xs text-gray-500">
        A list of instructions to be used by the evaluator's model. It will
        'think' through each of these steps in order before generating final
        scores.
      </div>
    </div>
    <FormList
      bind:content={instruction_items}
      content_label="Evaluation Step"
      empty_content={{ value: "" }}
      let:item_index
    >
      <FormElement
        label=""
        aria_label="Evaluation Step"
        inputType="textarea"
        id="judge_instruction_{item_index}"
        placeholder={instruction_placeholders[
          Math.min(item_index, instruction_placeholders.length - 1)
        ]}
        bind:value={instruction_items[item_index].value}
      />
    </FormList>

    <div class="flex flex-col gap-2">
      <div class="text-xl font-bold">Judge Prompt</div>
      <JudgePromptFields
        bind:judge_prompt
        bind:system_prompt
        {prompt_fetch_error}
        show_judge_instructions_variable={true}
      />
    </div>
  {:else}
    <Collapse title="Advanced: Judge Prompt">
      <JudgePromptFields
        bind:judge_prompt
        bind:system_prompt
        {prompt_fetch_error}
      />
    </Collapse>
  {/if}
</div>
