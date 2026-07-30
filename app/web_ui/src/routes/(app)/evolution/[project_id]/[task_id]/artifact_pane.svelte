<script lang="ts" context="module">
  import type { EvalConfig, TaskRunConfig } from "$lib/types"

  // What the inspector side pane is showing. Only one pane at a time; the
  // page replaces this wholesale.
  export type ArtifactPaneTarget =
    | { kind: "prompt"; title: string; prompt_ids: string[] }
    | { kind: "run_config"; run_config: TaskRunConfig }
    | { kind: "code" | "judge"; title: string; eval_config: EvalConfig }
</script>

<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { PromptResponse } from "$lib/types"
  import { available_tools, model_info, prompt_name_from_id } from "$lib/stores"
  import { getRunConfigUiProperties } from "$lib/utils/run_config_formatters"
  import { extractV2Props } from "$lib/utils/eval_types/registry"
  import Output from "$lib/ui/output.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import CloseIcon from "$lib/ui/icons/close_icon.svelte"
  import EvalConfigInstruction from "$lib/components/eval_config_instruction.svelte"
  import CodeEditor from "$lib/components/code_editor.svelte"

  export let target: ArtifactPaneTarget
  export let project_id: string
  export let task_id: string
  export let prompts: PromptResponse | null = null

  const dispatch = createEventDispatcher<{ close: undefined }>()

  const KIND_LABELS: Record<ArtifactPaneTarget["kind"], string> = {
    prompt: "Prompt",
    run_config: "Run Config",
    code: "Code Eval",
    judge: "Judge",
  }

  $: pane_name =
    target.kind === "prompt"
      ? target.title
      : target.kind === "run_config"
        ? target.run_config.name
        : target.title

  function prompt_text(prompt_id: string): string | null {
    return (
      prompts?.prompts.find((prompt) => prompt.id === prompt_id)?.prompt ?? null
    )
  }
</script>

<!-- Sized by its container: the page mounts this as a fixed right-side drawer. -->
<div class="h-full w-full bg-white flex flex-col overflow-hidden">
  <!-- Header -->
  <div class="flex items-start gap-2 px-4 pt-4 pb-2 flex-none">
    <div class="min-w-0 flex-1">
      <div class="text-[10px] uppercase tracking-wide text-gray-500">
        {KIND_LABELS[target.kind]}
      </div>
      <div class="font-medium text-gray-900 truncate" title={pane_name}>
        {pane_name}
      </div>
    </div>
    <button
      type="button"
      class="w-6 h-6 rounded-full flex items-center justify-center p-1.5 text-gray-500 hover:bg-gray-200 hover:text-gray-900 transition-colors flex-none"
      title="Close pane"
      on:click={() => dispatch("close")}
    >
      <CloseIcon />
    </button>
  </div>

  <div class="flex-1 overflow-y-auto px-4 pb-4">
    {#if target.kind === "prompt"}
      <div class="flex flex-col gap-4">
        {#each target.prompt_ids as prompt_id (prompt_id)}
          {@const text = prompt_text(prompt_id)}
          <div>
            <div
              class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1"
            >
              {prompt_name_from_id(prompt_id, prompts)}
            </div>
            {#if text}
              <Output raw_output={text} max_height={null} />
            {:else}
              <div class="text-sm text-gray-500">
                Prompt text is not available{prompt_id
                  ? ` for "${prompt_name_from_id(prompt_id, prompts)}"`
                  : ""}.
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {:else if target.kind === "run_config"}
      <PropertyList
        properties={getRunConfigUiProperties(
          project_id,
          task_id,
          target.run_config,
          $model_info,
          prompts,
          $available_tools,
        )}
      />
      {#if target.run_config.id}
        <div class="mt-4">
          <a
            class="btn btn-sm btn-outline"
            href={`/optimize/${project_id}/${task_id}/run_config/${target.run_config.id}`}
          >
            Open full page
          </a>
        </div>
      {/if}
    {:else if target.kind === "code" || target.kind === "judge"}
      {@const code_props = extractV2Props(target.eval_config, "code_eval")}
      {#if code_props?.code}
        <CodeEditor value={code_props.code} readonly={true} />
      {:else}
        <EvalConfigInstruction eval_config={target.eval_config} />
      {/if}
    {/if}
  </div>
</div>
