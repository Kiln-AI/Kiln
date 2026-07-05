<script lang="ts">
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import RunInputFormElement from "$lib/components/run_input_form_element.svelte"
  import {
    model_from_schema,
    type SchemaModelProperty,
  } from "$lib/utils/json_schema_editor/json_schema_templates"
  import Output from "$lib/ui/output.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import { grantCodeEvalTrust } from "$lib/api/v2_eval_api"
  import type { TestCodeToolResponse } from "$lib/types"
  import posthog from "posthog-js"

  export let project_id: string
  export let tool_function_name: string
  export let tool_description: string
  export let parameters_schema: { [key: string]: unknown }
  export let code: string
  export let timeout_seconds: number
  export let tool_allowlist: string[]

  let test_loading = false
  let test_result: TestCodeToolResponse | null = null
  let test_error: KilnError | null = null
  let trust_dialog: Dialog
  let abort_controller: AbortController | null = null

  // Track whether a successful test has run since last edit
  export let has_tested = false

  $: schema_model = parse_schema(parameters_schema)
  $: has_params = schema_model?.properties && schema_model.properties.length > 0

  let input_components: Record<string, RunInputFormElement> = {}

  function parse_schema(
    schema: { [key: string]: unknown } | undefined,
  ): SchemaModelProperty | null {
    if (!schema) return null
    try {
      const model = model_from_schema(
        schema as Parameters<typeof model_from_schema>[0],
      )
      return model
    } catch {
      return null
    }
  }

  function build_params(): { [key: string]: unknown } {
    if (!has_params) return {}
    const params: Record<string, unknown> = {}
    for (const [id, component] of Object.entries(input_components)) {
      const val = component.buildValue()
      if (val !== undefined) {
        params[id] = val
      }
    }
    return params
  }

  async function run_test() {
    test_loading = true
    test_result = null
    test_error = null

    let params: { [key: string]: unknown }
    try {
      params = build_params()
    } catch (e) {
      test_error = createKilnError(e)
      test_loading = false
      return
    }

    abort_controller = new AbortController()

    try {
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/test_code_tool",
        {
          params: {
            path: { project_id },
          },
          body: {
            tool_function_name,
            tool_description: tool_description || "test",
            parameters_schema,
            code,
            timeout_seconds,
            tool_allowlist: tool_allowlist || [],
            params,
          },
          signal: abort_controller.signal,
        },
      )

      if (error) {
        throw error
      }

      if (data.not_trusted) {
        trust_dialog.show()
        test_loading = false
        return
      }

      test_result = data
      has_tested = true
      posthog.capture("test_code_tool", {
        project_id,
        tool_function_name,
        success: !data.error,
      })
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        // User cancelled
      } else {
        test_error = createKilnError(e)
      }
    } finally {
      test_loading = false
      abort_controller = null
    }
  }

  function cancel_test() {
    if (abort_controller) {
      abort_controller.abort()
      abort_controller = null
    }
    test_loading = false
  }

  async function grant_trust_and_retry(): Promise<boolean> {
    try {
      await grantCodeEvalTrust(project_id)
    } catch (e) {
      test_error = createKilnError(e)
      return false
    }
    run_test()
    return true
  }
</script>

<div class="flex flex-col gap-3" data-testid="code-tool-test-panel">
  <div>
    <div class="text-xl font-bold">Test</div>
    <!-- TODO: security-related string — human sign-off required to finalize/remove -->
    <p class="text-sm text-gray-500 mt-0.5">
      Runs your code live against real tools — side effects included.
    </p>
  </div>

  {#if has_params && schema_model?.properties}
    <div class="flex flex-col gap-4">
      {#each schema_model.properties as prop}
        <RunInputFormElement
          property={prop}
          path={prop.id}
          bind:this={input_components[prop.id]}
        />
      {/each}
    </div>
  {/if}

  {#if test_loading}
    <div
      class="flex flex-col items-center gap-3 py-8"
      data-testid="running-state"
    >
      <span class="loading loading-spinner loading-md text-primary"></span>
      <div class="text-sm font-medium">Running...</div>
      <p class="text-xs text-gray-500">Executing your code tool</p>
      <button
        type="button"
        class="btn btn-sm btn-outline mt-1"
        on:click={cancel_test}
        data-testid="cancel-run"
      >
        Cancel
      </button>
    </div>
  {:else if test_result}
    {#if test_result.result !== null && test_result.result !== undefined}
      <div class="flex flex-col gap-1" data-testid="test-output">
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium">Output</span>
          {#if test_result.duration_ms}
            <span class="text-xs text-gray-400"
              >{(test_result.duration_ms / 1000).toFixed(1)}s</span
            >
          {/if}
        </div>
        <Output raw_output={test_result.result} max_height="200px" />
      </div>
    {/if}

    {#if test_result.error}
      <div class="flex flex-col gap-1" data-testid="test-error-result">
        <span class="text-sm font-medium text-error">Error</span>
        <div class="bg-error/10 rounded-lg p-3 text-sm">
          <p class="font-mono text-xs whitespace-pre-wrap">
            {test_result.error}
          </p>
          {#if test_result.traceback}
            <details class="mt-2">
              <summary class="text-xs text-gray-500 cursor-pointer"
                >Traceback</summary
              >
              <pre
                class="text-xs font-mono whitespace-pre-wrap mt-1 text-gray-600">{test_result.traceback}</pre>
            </details>
          {/if}
        </div>
        {#if test_result.duration_ms}
          <span class="text-xs text-gray-400"
            >{(test_result.duration_ms / 1000).toFixed(1)}s</span
          >
        {/if}
      </div>
    {/if}

    {#if test_result.tool_call_log && test_result.tool_call_log.length > 0}
      <div class="flex flex-col gap-1" data-testid="tool-call-log">
        <span class="text-sm font-medium">Tool Calls</span>
        <div class="overflow-x-auto rounded-lg border">
          <table class="table table-xs">
            <thead>
              <tr>
                <th>Function</th>
                <th>Arguments</th>
                <th>Duration</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {#each test_result.tool_call_log as entry}
                <tr>
                  <td class="font-mono text-xs">{entry.tool_name}</td>
                  <td class="text-xs max-w-[120px]">
                    <details>
                      <summary class="cursor-pointer truncate"
                        >{JSON.stringify(entry.arguments)}</summary
                      >
                      <pre
                        class="whitespace-pre-wrap font-mono mt-1">{JSON.stringify(
                          entry.arguments,
                          null,
                          2,
                        )}</pre>
                    </details>
                  </td>
                  <td class="text-xs">{entry.duration_ms}ms</td>
                  <td class="text-xs">
                    {#if entry.is_error}
                      <span class="badge badge-error badge-xs">Error</span>
                    {:else}
                      <span class="badge badge-success badge-xs">OK</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}

    {#if test_result.stdout}
      <details class="text-sm" data-testid="test-stdout">
        <summary class="cursor-pointer text-gray-500 text-xs font-medium"
          >stdout</summary
        >
        <pre
          class="bg-base-200 rounded-lg p-3 text-xs font-mono whitespace-pre-wrap mt-1 max-h-40 overflow-y-auto">{test_result.stdout}</pre>
      </details>
    {/if}

    {#if test_result.stderr}
      <details class="text-sm" data-testid="test-stderr">
        <summary class="cursor-pointer text-gray-500 text-xs font-medium"
          >stderr</summary
        >
        <pre
          class="bg-base-200 rounded-lg p-3 text-xs font-mono whitespace-pre-wrap mt-1 max-h-40 overflow-y-auto">{test_result.stderr}</pre>
      </details>
    {/if}

    <button
      type="button"
      class="btn btn-primary btn-outline btn-sm w-full"
      on:click={run_test}
      data-testid="run-again"
    >
      Run Again
    </button>
  {:else}
    <button
      type="button"
      class="btn btn-primary btn-outline btn-sm w-full"
      on:click={run_test}
      data-testid="run-test-btn"
    >
      Run Test
    </button>
  {/if}

  {#if test_error}
    <div data-testid="test-error">
      <Warning
        warning_color="error"
        tight
        warning_message={test_error.getMessage()}
      />
    </div>
  {/if}
</div>

<!-- TODO: replace with real trust mechanism (Phase 6) -->
<Dialog
  bind:this={trust_dialog}
  title="Trust Code and Project?"
  action_buttons={[
    {
      label: "Run — I Trust This Code",
      isWarning: true,
      asyncAction: grant_trust_and_retry,
    },
  ]}
>
  <div class="flex flex-row items-start gap-4">
    <svg
      class="w-10 h-10 text-warning flex-none"
      fill="currentColor"
      viewBox="0 0 256 256"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M128,20.00012a108,108,0,1,0,108,108A108.12217,108.12217,0,0,0,128,20.00012Zm0,192a84,84,0,1,1,84-84A84.0953,84.0953,0,0,1,128,212.00012Zm-12-80v-52a12,12,0,1,1,24,0v52a12,12,0,1,1-24,0Zm28,40a16,16,0,1,1-16-16A16.018,16.018,0,0,1,144,172.00012Z"
      />
    </svg>
    <div class="flex flex-col gap-2 text-sm text-left">
      <p>
        This project wants to run Python code on your machine. Only proceed if
        you trust the code and this project.
      </p>
      <p class="font-bold">Never paste code from a stranger or the internet.</p>
    </div>
  </div>
</Dialog>
