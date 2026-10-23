<script lang="ts" context="module">
  import type { EvalConfig, TaskRunConfig } from "$lib/types"

  // What the artifact modal is showing. Only one at a time; the page replaces
  // this wholesale.
  export type ArtifactPaneTarget =
    | { kind: "prompt"; title: string; prompt_ids: string[] }
    | { kind: "run_config"; run_config: TaskRunConfig }
    | { kind: "code" | "judge"; title: string; eval_config: EvalConfig }
</script>

<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte"
  import type { PromptResponse } from "$lib/types"
  import { available_tools, model_info, prompt_name_from_id } from "$lib/stores"
  import { getRunConfigUiProperties } from "$lib/utils/run_config_formatters"
  import { extractV2Props } from "$lib/utils/eval_types/registry"
  import Dialog from "$lib/ui/dialog.svelte"
  import Output from "$lib/ui/output.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import EvalConfigInstruction from "$lib/components/eval_config_instruction.svelte"
  import CodeEditor from "$lib/components/code_editor.svelte"

  export let target: ArtifactPaneTarget
  export let project_id: string
  export let task_id: string
  export let prompts: PromptResponse | null = null

  const dispatch = createEventDispatcher<{ close: undefined }>()

  let dialog: Dialog | null = null

  onMount(() => {
    dialog?.show()
  })

  // Kind label shown under the dialog title. A prompt target's own title
  // already names the artifact ("Prompt", "Prompt comparison"), so it gets
  // none rather than a subtitle repeating the heading.
  const KIND_LABELS: Partial<Record<ArtifactPaneTarget["kind"], string>> = {
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
  $: pane_subtitle = KIND_LABELS[target.kind] ?? null

  function prompt_text(prompt_id: string): string | null {
    return (
      prompts?.prompts.find((prompt) => prompt.id === prompt_id)?.prompt ?? null
    )
  }
</script>

<!-- A modal, not a drawer: the detail panel owns the right-hand column of the
     graph card, and prompt text / property lists read better wide. The modal
     box scrolls its own content, so long prompts stay inside it. -->
<Dialog
  bind:this={dialog}
  title={pane_name}
  subtitle={pane_subtitle}
  width="wide"
  on:close={() => dispatch("close")}
>
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
</Dialog>
