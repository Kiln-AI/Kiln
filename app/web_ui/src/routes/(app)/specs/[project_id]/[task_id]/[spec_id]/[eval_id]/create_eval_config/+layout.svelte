<script lang="ts">
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, setContext } from "svelte"
  import { writable } from "svelte/store"
  import type { Eval, Task, Spec } from "$lib/types"
  import { load_task, load_available_models } from "$lib/stores"
  import { ALL_V2_EVAL_TYPES } from "$lib/utils/eval_types/registry"
  import {
    CREATE_EVAL_LAYOUT_KEY,
    type CreateEvalLayoutContext,
  } from "./context"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: eval_id = $page.params.eval_id!
  $: spec_id = $page.params.spec_id!

  let spec: Spec | null = null
  let spec_loading = true
  let spec_error: KilnError | null = null

  let evaluator: Eval | undefined = undefined
  let task: Task | null = null

  let loading_eval = true
  let loading_eval_error: KilnError | undefined = undefined
  let loading_task = true
  let loading_task_error: KilnError | undefined = undefined
  $: loading = loading_eval || loading_task || spec_loading
  $: loading_error = loading_eval_error || loading_task_error || spec_error

  const evalStore = writable<Eval | undefined>(undefined)
  const taskStore = writable<Task | null>(null)
  const specStore = writable<Spec | null>(null)
  const projectIdStore = writable<string>("")
  const taskIdStore = writable<string>("")
  const evalIdStore = writable<string>("")
  const specIdStore = writable<string>("")

  $: evalStore.set(evaluator)
  $: taskStore.set(task)
  $: specStore.set(spec)
  $: projectIdStore.set(project_id)
  $: taskIdStore.set(task_id)
  $: evalIdStore.set(eval_id)
  $: specIdStore.set(spec_id)

  const layoutContext: CreateEvalLayoutContext = {
    evaluator: evalStore,
    task: taskStore,
    spec: specStore,
    project_id: projectIdStore,
    task_id: taskIdStore,
    eval_id: evalIdStore,
    spec_id: specIdStore,
  }
  setContext(CREATE_EVAL_LAYOUT_KEY, layoutContext)

  onMount(async () => {
    await handle_legacy_redirect()
    await Promise.all([load_eval(), get_spec(), load_available_models()])
    await load_task_local()
  })

  async function handle_legacy_redirect() {
    const config_type_param = $page.url.searchParams.get("config_type")
    if (!config_type_param) return

    let target_type: string | null = null
    if (
      config_type_param === "g_eval" ||
      config_type_param === "llm_as_judge"
    ) {
      target_type = "llm_judge"
    } else if (
      ALL_V2_EVAL_TYPES.includes(
        config_type_param as (typeof ALL_V2_EVAL_TYPES)[number],
      )
    ) {
      target_type = config_type_param
    }

    if (target_type) {
      const params = new URLSearchParams($page.url.searchParams)
      params.delete("config_type")
      const query = params.toString()
      const base = $page.url.pathname.replace(/\/$/, "")
      await goto(`${base}/${target_type}${query ? "?" + query : ""}`, {
        replaceState: true,
      })
    }
  }

  async function get_spec() {
    if (spec_id === "legacy") {
      spec_loading = false
      return
    }
    try {
      spec_loading = true
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        {
          params: {
            path: {
              project_id: project_id,
              task_id: task_id,
              spec_id: spec_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      spec = data
    } catch (error) {
      spec_error = createKilnError(error)
    } finally {
      spec_loading = false
    }
  }

  async function load_task_local() {
    try {
      loading_task = true
      if (!evaluator) {
        loading_task_error = createKilnError(
          new Error("Evaluator not loaded, can not load task"),
        )
        return
      }

      task = await load_task(project_id, task_id)
      if (!task) {
        throw new Error("Task not found")
      }
    } catch (e) {
      loading_task_error = createKilnError(e)
    } finally {
      loading_task = false
    }
  }

  async function load_eval() {
    try {
      loading_eval = true
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
              eval_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      evaluator = data
    } catch (e) {
      loading_eval_error = createKilnError(e)
    } finally {
      loading_eval = false
    }
  }
</script>

{#if loading}
  <div class="max-w-[1400px]">
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  </div>
{:else if loading_error}
  <div class="max-w-[1400px]">
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Task Information</div>
      <div class="text-error text-sm">
        {loading_error?.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  </div>
{:else}
  <slot />
{/if}
