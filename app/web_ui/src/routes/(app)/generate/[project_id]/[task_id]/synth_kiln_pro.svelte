<script lang="ts">
  import { onMount, onDestroy, tick } from "svelte"
  import { get } from "svelte/store"
  import Intro from "$lib/ui/intro.svelte"
  import ConnectKilnCopilotSteps from "$lib/ui/kiln_copilot/connect_kiln_copilot_steps.svelte"
  import { checkKilnCopilotAvailable } from "$lib/utils/copilot_utils"
  import RefiningAnimation from "$lib/ui/animations/refining_animation.svelte"
  import IncrementUi from "$lib/ui/increment_ui.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import { isKilnAgentRunConfig } from "$lib/types"
  import type { KilnAgentRunConfigProperties } from "$lib/types"
  import { KilnError } from "$lib/utils/error_handlers"
  import SynthDataGuide from "./synth_data_guide.svelte"
  import KilnProBatchPlan from "./kiln_pro_batch_plan.svelte"
  import KilnProInputs from "./kiln_pro_inputs.svelte"
  import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"

  export let project_id: string
  export let task_id: string
  export let guidance_data: SynthDataGuidanceDataModel

  const selected_template = guidance_data.selected_template
  $: task = guidance_data.task

  const dialog_id = "generate_batch_dialog"
  const inputs_dialog_id = "kiln_pro_generate_inputs_dialog"

  let current_state: "loading" | "connect" | "ready" = "loading"
  let connect_success = false

  // Stage within the connected flow.
  let stage: "intro" | "planning" | "plan" | "inputs" = "intro"

  let num_inputs = 8
  // Saved for the session so Regenerate reopens the modal with the user's edits.
  let batch_guidance = ""
  let guidance_initialized = false
  // The dialog stays mounted across reopens, so we own this flag and reset it
  // on submit — otherwise the spinner persists into the next Regenerate.
  let batch_submitting = false

  type BatchPlan = { prompts: string[]; summary: string }
  let plan: BatchPlan | null = null
  // True once the user edits the plan (deletes prompts); the summary isn't
  // regenerated so we flag it as possibly out of date.
  let plan_edited = false

  let planning_timer: ReturnType<typeof setTimeout> | null = null

  // Generate Inputs modal lives here (not in the inputs view) so it opens over
  // the plan page — the page only transitions once the user submits it.
  let inputs_run_config: RunConfigComponent | null = null
  let inputs_submitting = false
  let inputs_error: KilnError | null = null
  let inputs_rcp: KilnAgentRunConfigProperties | null = null
  let inputs_data_guide: string | null = null

  onMount(async () => {
    try {
      current_state = (await checkKilnCopilotAvailable()) ? "ready" : "connect"
    } catch {
      current_state = "connect"
    }
  })

  onDestroy(() => {
    if (planning_timer) clearTimeout(planning_timer)
  })

  function handle_connect_success() {
    connect_success = true
  }

  function proceed_after_connect() {
    current_state = "ready"
    connect_success = false
  }

  async function open_generate_batch_modal() {
    if (!guidance_initialized) {
      batch_guidance = guidance_data.kiln_pro_batch_plan_prefill()
      guidance_initialized = true
    }
    await tick()
    // @ts-expect-error showModal is not typed on HTMLElement
    document.getElementById(dialog_id)?.showModal()
  }

  // Dummy plan stand-in until the kiln_server call is wired in. The real
  // endpoint returns { prompts: string[], summary: string }.
  function make_dummy_plan(n: number): BatchPlan {
    return {
      prompts: Array.from({ length: n }, (_, i) => `Dummy prompt ${i + 1}`),
      summary: `**${n} prompts** that push this eval across the situations your users actually hit — with a deliberate mix of common cases and hard edges.\n\n- **40% Core scenarios** — the common, expected cases\n- **30% Variations** — phrasing, tone, and context shifts\n- **20% Edge cases** — boundary and adversarial inputs\n- **10% Negative controls** — inputs that should *not* trigger`,
    }
  }

  function submit_batch() {
    batch_submitting = false
    // @ts-expect-error close is not typed on HTMLElement
    document.getElementById(dialog_id)?.close()
    const requested = num_inputs
    stage = "planning"
    // Hard-coded 2s stand-in for the server call.
    planning_timer = setTimeout(() => {
      plan = make_dummy_plan(requested)
      plan_edited = false
      stage = "plan"
      planning_timer = null
    }, 2000)
  }

  function delete_prompt(index: number) {
    if (!plan) return
    plan = {
      ...plan,
      prompts: plan.prompts.filter((_, i) => i !== index),
    }
    plan_edited = true
  }

  async function open_inputs_modal() {
    inputs_error = null
    await tick()
    // @ts-expect-error showModal is not typed on HTMLElement
    document.getElementById(inputs_dialog_id)?.showModal()
  }

  // Capture the model config, then transition to the inputs view (which starts
  // generation). The plan page stays put until this submit fires.
  function submit_inputs() {
    inputs_submitting = false
    const rcp =
      inputs_run_config?.run_options_as_run_config_properties() ?? null
    if (!rcp || !isKilnAgentRunConfig(rcp)) {
      inputs_error = new KilnError(
        "Synthetic data generation requires a model with a kiln_agent run config.",
        null,
      )
      return
    }
    inputs_rcp = rcp
    inputs_data_guide = get(guidance_data.use_data_guide)
      ? get(guidance_data.data_guide)
      : null
    // @ts-expect-error close is not typed on HTMLElement
    document.getElementById(inputs_dialog_id)?.close()
    stage = "inputs"
  }
</script>

{#if current_state === "loading"}
  <div class="flex justify-center items-center min-h-[50vh]">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
{:else if current_state === "connect"}
  <div
    class="flex flex-col max-w-[400px] mx-auto mt-24 md:mt-36 border border-base-300 rounded-2xl bg-base-100 px-6 shadow-lg py-8 md:py-12"
  >
    <ConnectKilnCopilotSteps
      onSuccess={handle_connect_success}
      showCheckmark={connect_success}
    />
    {#if connect_success}
      <button
        class="btn btn-primary mt-4 btn-wide mx-auto"
        on:click={proceed_after_connect}
      >
        Continue
      </button>
    {/if}
  </div>
{:else if stage === "planning"}
  <div class="flex flex-col items-center justify-center min-h-[50vh] mt-12">
    <RefiningAnimation
      title="Planning Batch"
      description={`Kiln is drafting ${num_inputs} tailored prompts for you to review. This may take a while.`}
    />
  </div>
{:else if stage === "plan" && plan}
  <KilnProBatchPlan
    {plan}
    on_generate_inputs={open_inputs_modal}
    on_regenerate={open_generate_batch_modal}
    on_delete_prompt={delete_prompt}
    summary_out_of_sync={plan_edited}
  />
{:else if stage === "inputs" && plan && inputs_rcp}
  <KilnProInputs
    {plan}
    {project_id}
    {task_id}
    {guidance_data}
    run_config_properties={inputs_rcp}
    data_guide={inputs_data_guide}
    summary_out_of_sync={plan_edited}
  />
{:else}
  <div class="flex flex-col items-center justify-center min-h-[50vh] mt-12">
    <Intro
      title="Plan your batch before you generate"
      description_paragraphs={[
        "Tell Kiln what you want and how many inputs you need. Kiln Pro drafts a plan up front — a short summary plus one tailored prompt per input — balancing variety, edge cases, and emphasis so your batch is intentional rather than random.",
        "You'll review and trim the prompts before a single input is generated.",
      ]}
      action_buttons={[
        {
          label: "Generate Batch",
          is_primary: true,
          onClick: open_generate_batch_modal,
        },
        {
          label: "Guide",
          is_primary: false,
          href: `/generate/${project_id}/${task_id}/data_guide`,
        },
      ]}
    >
      <div slot="icon" class="h-12 w-12">
        <img src="/images/animated_logo.svg" alt="Kiln Pro" />
      </div>
    </Intro>
  </div>
{/if}

<dialog id={dialog_id} class="modal">
  <div class="modal-box w-11/12 max-w-3xl">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-bold">Generate Batch</h3>
    <p class="text-sm font-light mb-8">
      Kiln Pro will draft a batch plan — a short summary plus one tailored
      prompt per input — for you to review before any inputs are generated.
    </p>
    <FormContainer
      submit_label="Generate Batch"
      bind:submitting={batch_submitting}
      on:submit={submit_batch}
    >
      <div class="flex flex-row items-center gap-4">
        <div class="flex-grow font-medium text-sm">Input Count</div>
        <IncrementUi bind:value={num_inputs} max={500} />
      </div>
      <FormElement
        id="batch_guidance"
        label="Guidance"
        inputType="textarea"
        height="xl"
        bind:value={batch_guidance}
      />
      <SynthDataGuide {guidance_data} />
    </FormContainer>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>

<dialog id={inputs_dialog_id} class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-bold">Generate Inputs</h3>
    <p class="text-sm font-light mb-5">
      {#if plan}
        Kiln Pro will generate {plan.prompts.length} inputs in parallel — one per
        planned prompt.
      {/if}
    </p>
    {#if inputs_error}
      <div class="text-error text-sm mb-3">{inputs_error.getMessage()}</div>
    {/if}
    <FormContainer
      submit_label={plan
        ? `Generate ${plan.prompts.length} Inputs`
        : "Generate"}
      bind:submitting={inputs_submitting}
      on:submit={submit_inputs}
    >
      {#if task}
        <RunConfigComponent
          bind:this={inputs_run_config}
          {project_id}
          current_task={task}
          requires_structured_output={true}
          hide_prompt_selector={true}
          show_tools_selector_in_advanced={true}
          show_name_field={false}
          model_dropdown_settings={{
            requires_data_gen: true,
            requires_uncensored_data_gen:
              guidance_data.suggest_uncensored($selected_template),
            suggested_mode: guidance_data.suggest_uncensored($selected_template)
              ? "uncensored_data_gen"
              : "data_gen",
          }}
        />
      {/if}
      <SynthDataGuide {guidance_data} />
    </FormContainer>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
