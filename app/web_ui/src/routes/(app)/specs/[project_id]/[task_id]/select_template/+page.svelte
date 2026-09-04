<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import type { ComponentType } from "svelte"
  import AppPage from "../../../../app_page.svelte"
  import OptionList from "$lib/ui/option_list.svelte"
  import type { OptionListItem } from "$lib/ui/option_list_types"
  import SettingsHeader from "$lib/ui/settings_header.svelte"
  import { formatSpecTypeName } from "$lib/utils/formatters"
  import { spec_categories } from "./spec_templates"
  import type { SpecTemplateData } from "./spec_templates"
  import {
    next_page_after_template,
    judge_only_builder_url,
  } from "../spec_utils"
  import { agentInfo } from "$lib/agent"
  import Collapse from "$lib/ui/collapse.svelte"
  import Intro from "$lib/ui/intro.svelte"
  import EvalIcon from "$lib/ui/icons/eval_icon.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { kilnCopilotConnected } from "$lib/stores/copilot_connection_store"
  import { getV2EvalTypeMetadata } from "$lib/utils/eval_types/registry"
  import type { V2EvalType } from "$lib/utils/eval_types/registry"
  import { getEvalTypeIconComponent } from "$lib/components/eval_types/eval_type_icon.svelte"
  import type { SpecType } from "$lib/types"

  import DesiredBehaviourIcon from "$lib/ui/icons/spec_types/desired_behaviour_icon.svelte"
  import IssueIcon from "$lib/ui/icons/spec_types/issue_icon.svelte"
  import ToxicityIcon from "$lib/ui/icons/spec_types/toxicity_icon.svelte"
  import QnaIcon from "$lib/ui/icons/qna_icon.svelte"
  import BookIcon from "$lib/ui/icons/book_icon.svelte"
  import ScalesIcon from "$lib/ui/icons/scales_icon.svelte"
  import ShieldIcon from "$lib/ui/icons/shield_icon.svelte"
  import KeyIcon from "$lib/ui/icons/key_icon.svelte"

  // ### Spec Template Select ###

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: agentInfo.set({
    name: "Select Eval Type",
    description: `Select an eval type as part of the eval creation process for project ID ${project_id}, task ID ${task_id}. Choose from available eval types.`,
  })

  function select_template(template_data: SpecTemplateData) {
    goto(next_page_after_template(project_id, task_id, template_data.spec_type))
  }

  // The programmatic checks section: judges chosen directly, without a
  // template. All of them create spec-less, template-less evals via the spec
  // builder's judge-only mode — the judge form collects any config it needs
  // (e.g. the tool list for Tool Call Check). The legacy "tool_call" template
  // is reserved for pre-spec LLM tool evals and is never recorded on new ones.
  const programmatic_judge_types: V2EvalType[] = [
    "code_eval",
    "tool_call_check",
    "exact_match",
    "pattern_match",
    "contains",
    "set_check",
    "step_count_check",
  ]

  const template_icons: Partial<Record<SpecType, ComponentType>> = {
    desired_behaviour: DesiredBehaviourIcon,
    issue: IssueIcon,
    reference_answer_accuracy: QnaIcon,
    factual_correctness: BookIcon,
    toxicity: ToxicityIcon,
    bias: ScalesIcon,
    maliciousness: ShieldIcon,
    jailbreak: KeyIcon,
  }

  const all_templates = spec_categories.flatMap(
    (category) => category.templates,
  )
  // Tool use is offered as the Tool Call Check programmatic judge, not an LLM
  // template.
  const llm_templates = all_templates.filter(
    (t) => t.spec_type !== "appropriate_tool_use",
  )

  const llm_options: OptionListItem[] = llm_templates.map((template_data) => ({
    id: template_data.spec_type,
    name: formatSpecTypeName(template_data.spec_type),
    description: template_data.description,
    icon: template_icons[template_data.spec_type],
  }))

  const programmatic_options: OptionListItem[] = programmatic_judge_types.map(
    (judge_type) => {
      const metadata = getV2EvalTypeMetadata(judge_type)
      return {
        id: judge_type,
        name: metadata.label,
        description: metadata.description,
        icon: getEvalTypeIconComponent(judge_type),
        tags: metadata.tags,
      }
    },
  )

  function select_llm_option(id: string) {
    const template_data = llm_templates.find((t) => t.spec_type === id)
    if (template_data) {
      select_template(template_data)
    }
  }

  function select_programmatic_option(id: string) {
    goto(judge_only_builder_url(project_id, task_id, id as V2EvalType))
  }

  // PREVIEW (09-03): the entry restructure. Both user types land here instead
  // of Pro users being sent straight to the builder, so the eval type and the
  // free-text description are one decision rather than two screens.
  //
  // The textbox is the main UI for anyone with Copilot: it is the builder's
  // first step, hoisted onto this page so the templates and the programmatic
  // checks are visible beside it rather than behind a link that reads like
  // opting out. Without Copilot there is nothing to describe to, so the
  // template list stays the primary choice and this section is absent.
  let description = ""

  // Without Copilot the page opens on the offer rather than the templates.
  // The Pro-vs-manual question is asked once, up front, instead of partway
  // through after a template is already chosen. Choosing manual reveals the
  // same picker a Copilot user sees folded under "See templates".
  let chose_manual = false
  // The offer is showing, as opposed to the picker behind it. Named once so
  // the page title and the body can never describe different screens.
  $: show_offer = $kilnCopilotConnected !== true && !chose_manual

  function connect_kiln_pro() {
    goto("/specs/pro_auth")
  }

  function continue_with_description() {
    const text = description.trim()
    if (!text) return
    goto(
      `/specs/${project_id}/${task_id}/builder?description=${encodeURIComponent(text)}`,
    )
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Setup and Eval Type"
    subtitle={show_offer
      ? "Kiln Pro drafts the eval for you, or set one up yourself."
      : $kilnCopilotConnected === true
        ? "Describe what this eval should check, or pick a template or a programmatic check."
        : "Pick a template or a programmatic check."}
    breadcrumbs={[
      {
        label: "Evals",
        href: `/specs/${project_id}/${task_id}`,
      },
    ]}
  >
    {#if show_offer}
      <!-- The offer, before the templates. This is also the only place eval
           creation pitches Kiln Pro: the screen that used to carry that pitch
           sat partway through the old flow and is gone. -->
      <div class="flex justify-center mt-[10vh]">
        <Intro
          title="Let Kiln Pro write the eval"
          description_paragraphs={[
            "Describe what to check in plain language. Kiln Pro writes the eval, generates test data to run it on, and checks its judge against your own review.",
            "Or set one up yourself from a template.",
          ]}
          action_buttons={[
            {
              label: "Use Kiln Pro",
              onClick: connect_kiln_pro,
              is_primary: true,
            },
            {
              label: "Set Up Manually",
              onClick: () => (chose_manual = true),
              is_primary: false,
            },
          ]}
        >
          <div slot="icon" class="h-12 w-12">
            <EvalIcon />
          </div>
        </Intro>
      </div>
    {:else}
      <div class="pt-6 max-w-5xl flex flex-col gap-10">
        {#if $kilnCopilotConnected === true}
          <div class="flex flex-col gap-4">
            <SettingsHeader title="LLM Judge" />
            <FormElement
              label="What should this eval check?"
              description="Describe in plain language. Kiln asks a few questions, then builds the eval and its judge."
              id="eval_description"
              inputType="textarea"
              height="medium"
              bind:value={description}
            />
            <div class="flex justify-end">
              <button
                class="btn btn-primary min-w-48"
                disabled={!description.trim()}
                on:click={continue_with_description}
              >
                Continue
              </button>
            </div>
            <!-- The templates are the same list a user without Copilot gets as
               their primary choice. Folded here so the description leads,
               without hiding the option from someone who knows what they
               want. -->
            <Collapse title="See templates" outlined={true}>
              <OptionList
                options={llm_options}
                select_option={select_llm_option}
                two_columns={true}
                two_line_descriptions={true}
              />
            </Collapse>
          </div>
        {:else}
          <div class="flex flex-col gap-4">
            <SettingsHeader title="LLM Judges" />
            <OptionList
              options={llm_options}
              select_option={select_llm_option}
              two_columns={true}
              two_line_descriptions={true}
            />
          </div>
        {/if}
        <div class="flex flex-col gap-4">
          <SettingsHeader title="Programmatic Checks" />
          <OptionList
            options={programmatic_options}
            select_option={select_programmatic_option}
            two_columns={true}
            two_line_descriptions={true}
          />
        </div>
      </div>
    {/if}
  </AppPage>
</div>
