<script lang="ts">
  import { current_task, current_task_prompts } from "$lib/stores"
  import { page } from "$app/stores"
  import { type KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import { _ } from "svelte-i18n"
  import AppPage from "../../../../../app_page.svelte"
  import Output from "../../../../../run/output.svelte"

  let prompt: string | null = null
  let prompt_loading = true
  let prompt_error: KilnError | null = null

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: generator_id = $page.params.generator_id
  $: generator_name = $current_task_prompts?.generators.find(
    (generator) => generator.id === generator_id,
  )?.name
  $: generator_description = $current_task_prompts?.generators.find(
    (generator) => generator.id === generator_id,
  )?.description

  $: (() => {
    get_prompt(generator_id)
  })()

  async function get_prompt(prompt_generator: string | undefined) {
    if (!prompt_generator) {
      prompt = null
      return
    }
    try {
      prompt_loading = true
      const { data: prompt_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/task/{task_id}/gen_prompt/{prompt_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
              prompt_id: prompt_generator,
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
    title={$_("prompts.generator_details.title")}
    subtitle={generator_name}
  >
    {#if prompt_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if $current_task?.id != task_id}
      <div class="text-error">
        {$_("prompts.generator_details.task_link_error")}
      </div>
    {:else if prompt && !prompt_error}
      <div>
        <h2 class="text-sm font-medium mt-4 mb-1">
          {$_("prompts.generator_details.generator_description")}
        </h2>
        <p class="mb-6 text-sm text-gray-500">
          {generator_description}
        </p>

        <h2 class="text-sm font-medium mt-4 mb-1">
          {$_("prompts.generator_details.how_to_improve")}
        </h2>
        <p class="mb-6 text-sm text-gray-500">
          {$_("prompts.generator_details.improve_description")}
          <a href={`/settings/edit_task/${project_id}/${task_id}`} class="link"
            >{$_(
              "prompts.generator_details.edit_task_link_text",
            )}{generator_id !== "short_prompt_builder"
              ? $_("prompts.generator_details.requirements_text")
              : ""}</a
          ><span
            class={["simple_prompt_builder", "short_prompt_builder"].includes(
              generator_id,
            )
              ? "hidden"
              : ""}
            >{$_("prompts.generator_details.additional_improvement")}
            <a class="link" href="/run"
              >{$_("prompts.generator_details.run_link_text")}</a
            >{$_("prompts.generator_details.additional_improvement_suffix")}
          </span>
        </p>

        <h2 class="text-sm font-medium mt-4 mb-1">
          {$_("prompts.generator_details.generated_prompt")}
        </h2>
        <p class="mb-2 text-sm text-gray-500">
          {$_("prompts.generator_details.generated_prompt_description", {
            values: { generator_name },
          })}
        </p>
        <Output raw_output={prompt} />
      </div>
    {:else}
      <div class="text-error">
        {prompt_error?.getMessage() || $_("common.error")}
      </div>
    {/if}
  </AppPage>
</div>
