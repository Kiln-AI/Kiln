<script lang="ts">
  import Output from "../../../run/output.svelte"
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { current_task } from "$lib/stores"
  import type { Task } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import PromptTypeSelector from "../../../run/prompt_type_selector.svelte"
  import { goto } from "$app/navigation"

  let task: Task | null = null
  let task_error: KilnError | null = null
  let task_loading = true

  let prompt_method: string =
    $page.url.searchParams.get("prompt_generator") || "basic"
  let prompt: string | null = null
  let prompt_loading = false
  let prompt_error: KilnError | null = null

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  $: (() => {
    if (prompt_method) {
      get_prompt(prompt_method)
      const url = new URL($page.url)
      // save the value in the url so that it persists when navigating back to this page.
      url.searchParams.set("prompt_generator", prompt_method)
      // replace state so there aren't a ton of entries in the browser history / back stack
      goto(url.toString(), {
        replaceState: true,
        keepFocus: true,
        noScroll: true,
      })
    }
  })()

  onMount(async () => {
    get_task()
  })

  async function get_task() {
    try {
      task_loading = true
      if (!project_id || !task_id) {
        throw new Error("Project or task ID not set.")
      }
      if ($current_task?.id === task_id) {
        task = $current_task
        return
      }
      const { data: task_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      task = task_response
      get_prompt(prompt_method)
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        task_error = new KilnError(
          "Could not load task. It may belong to a project you don't have access to.",
          null,
        )
      } else {
        task_error = createKilnError(e)
      }
    } finally {
      task_loading = false
    }
  }

  async function get_prompt(prompt_generator: string) {
    try {
      prompt_loading = true
      const { data: prompt_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/task/{task_id}/gen_prompt/{prompt_generator}",
        {
          params: {
            path: {
              project_id,
              task_id,
              prompt_generator,
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      prompt = prompt_response.prompt
    } catch (e) {
      prompt_error = createKilnError(e)
    } finally {
      prompt_loading = false
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Prompts"
    subtitle={`Explore prompts for "${task?.name}"`}
    sub_subtitle="Kiln builds prompts based on data, not static text. Running prompts and rating the responses will improve your prompt quality using methods like few-shot and multi-shot prompting."
  >
    {#if task_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if task}
      <div class="flex flex-col gap-4">
        <PromptTypeSelector bind:prompt_method />
        {#if prompt_loading}
          <div class="w-full min-h-[50vh] flex justify-center items-center">
            <div class="loading loading-spinner loading-lg"></div>
          </div>
        {:else if prompt}
          <div>
            <h2 class="text-sm font-medium mt-4 mb-1">Prompt</h2>
            <p class="mb-6 text-sm text-gray-500">
              To improve the quality of this prompt, <a
                href={`/settings/edit_task/${project_id}/${task_id}`}
                class="link">edit the task instructions or requirements</a
              ><span class={prompt_method === "basic" ? "hidden" : ""}
                >, or add more data to your dataset by <a
                  class="link"
                  href="/run">running the task</a
                >, or add ratings and repairs to your
                <a class="link" href={`/dataset/${project_id}/${task_id}`}
                  >existing dataset</a
                ></span
              >.
            </p>
            <Output raw_output={prompt} />
          </div>
        {:else}
          <div class="text-error">
            {prompt_error?.getMessage() || "An unknown error occurred"}
          </div>
        {/if}
      </div>
    {:else if task_error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Task</div>
        <div class="text-error text-sm">
          {task_error.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {/if}
  </AppPage>
</div>
