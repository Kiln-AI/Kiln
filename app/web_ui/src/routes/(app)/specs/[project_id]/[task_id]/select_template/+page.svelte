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
  // template. Tool Call Check routes through its template so the eval records
  // template: "tool_call" (no spec is created — the judge form collects the
  // tool list); the rest create template-less evals via the spec builder's
  // judge-only mode.
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
  const tool_call_template = all_templates.find(
    (t) => t.spec_type === "appropriate_tool_use",
  )
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
    if (id === "tool_call_check" && tool_call_template) {
      select_template(tool_call_template)
      return
    }
    goto(judge_only_builder_url(project_id, task_id, id as V2EvalType))
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Select an Eval Type"
    subtitle="Select a template for what you want this task to enforce or avoid."
    breadcrumbs={[
      {
        label: "Evals",
        href: `/specs/${project_id}/${task_id}`,
      },
    ]}
  >
    <div class="pt-6 max-w-5xl flex flex-col gap-10">
      <div class="flex flex-col gap-4">
        <SettingsHeader title="LLM Judges" />
        <OptionList
          options={llm_options}
          select_option={select_llm_option}
          two_columns={true}
          two_line_descriptions={true}
        />
      </div>
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
  </AppPage>
</div>
