<script lang="ts">
  import type { Task } from "$lib/types"
  import Output from "../../../../(app)/run/output.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import SchemaSection from "./schema_section.svelte"
  import { current_project } from "$lib/stores"
  import { goto } from "$app/navigation"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { ui_state, projects } from "$lib/stores"
  import { get } from "svelte/store"
  import { client } from "$lib/api_client"
  import { tick } from "svelte"
  import { _ } from "svelte-i18n"

  // Prevents flash of complete UI if we're going to redirect
  export let redirect_on_created: string | null = "/"
  export let hide_example_task: boolean = false

  // @ts-expect-error This is a partial task, which is fine.
  export let task: Task = {
    name: "",
    description: "",
    instruction: "",
    requirements: [],
  }

  $: creating = !task.id
  $: editing = !creating
  $: show_requirements = editing || task.requirements.length > 0

  // These have their own custom VM, which is translated back to the model on save
  let outputSchemaSection: SchemaSection
  let inputSchemaSection: SchemaSection

  let error: KilnError | null = null
  let submitting = false
  export let saved: boolean = false

  // Warn before unload if there's any user input
  $: warn_before_unload =
    !saved &&
    ([task.name, task.description, task.instruction].some((value) => !!value) ||
      task.requirements.some((req) => !!req.name || !!req.instruction))

  // Allow explicitly setting project ID, or infer current project ID
  export let explicit_project_id: string | undefined = undefined
  $: target_project_id = explicit_project_id || $current_project?.id || null

  export let project_target_name: string | null = null
  $: {
    if (!target_project_id) {
      project_target_name = null
    } else {
      project_target_name =
        $projects?.projects.find((p) => p.id === target_project_id)?.name ||
        $_("task.edit_task_page.project_id_prefix") + target_project_id
    }
  }

  async function create_task() {
    try {
      saved = false
      if (!target_project_id) {
        error = new KilnError(
          $_("task.edit_task_page.project_required_error"),
          null,
        )
        return
      }
      let body: Record<string, unknown> = {
        name: task.name,
        description: task.description,
        instruction: task.instruction,
        requirements: task.requirements,
        thinking_instruction: task.thinking_instruction,
      }
      // Can only set schemas when creating a new task
      if (creating) {
        body.input_json_schema = inputSchemaSection.get_schema_string()
        body.output_json_schema = outputSchemaSection.get_schema_string()
      }
      const project_id = target_project_id
      if (!project_id) {
        throw new KilnError(
          $_("task.edit_task_page.current_project_not_found"),
          null,
        )
      }
      let data: Task | undefined
      let network_error: unknown | null = null
      if (creating) {
        const { data: post_data, error: post_error } = await client.POST(
          "/api/projects/{project_id}/task",
          {
            params: {
              path: {
                project_id,
              },
            },
            // @ts-expect-error This API is not typed
            body: body,
          },
        )
        data = post_data
        network_error = post_error
      } else {
        const { data: patch_data, error: patch_error } = await client.PATCH(
          "/api/projects/{project_id}/task/{task_id}",
          {
            params: {
              path: {
                project_id,
                task_id: task.id || "",
              },
            },
            // @ts-expect-error This API is not typed
            body: body,
          },
        )
        data = patch_data
        network_error = patch_error
      }
      if (network_error || !data) {
        throw network_error
      }

      error = null
      // Make this the current task
      ui_state.set({
        ...get(ui_state),
        current_task_id: data.id,
        current_project_id: target_project_id,
      })
      saved = true
      // Wait for the saved change to propagate to the warn_before_unload
      await tick()
      if (redirect_on_created) {
        goto(redirect_on_created)
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }

  export function has_edits(): boolean {
    let has_edited_requirements = task.requirements.some(
      (req) => !!req.name || !!req.instruction,
    )
    return (
      !!task.name ||
      !!task.description ||
      !!task.instruction ||
      !!task.thinking_instruction ||
      has_edited_requirements ||
      !!inputSchemaSection.get_schema_string() ||
      !!outputSchemaSection.get_schema_string()
    )
  }

  function example_task() {
    if (has_edits()) {
      if (!confirm($_("task.edit_task_page.replace_edits_confirm"))) {
        return
      }
    }

    // @ts-expect-error This is a partial task, which is fine.
    task = {
      name: $_("task.edit_task_page.example_task_name"),
      description: $_("task.edit_task_page.example_task_description"),
      instruction: $_("task.edit_task_page.example_task_instruction"),
      requirements: [],
      input_json_schema: JSON.stringify({
        type: "object",
        properties: {
          joke_topic: {
            title: $_("task.edit_task_page.example_joke_topic_title"),
            type: "string",
            description: $_(
              "task.edit_task_page.example_joke_topic_description",
            ),
          },
          joke_style: {
            title: $_("task.edit_task_page.example_joke_style_title"),
            type: "string",
            description: $_(
              "task.edit_task_page.example_joke_style_description",
            ),
          },
        },
        required: ["joke_topic"],
      }),
      output_json_schema: JSON.stringify({
        type: "object",
        properties: {
          setup: {
            title: $_("task.edit_task_page.example_setup_title"),
            type: "string",
            description: $_("task.edit_task_page.example_setup_description"),
          },
          punchline: {
            title: $_("task.edit_task_page.example_punchline_title"),
            type: "string",
            description: $_(
              "task.edit_task_page.example_punchline_description",
            ),
          },
        },
        required: ["setup", "punchline"],
      }),
    }
  }

  function prompt_description() {
    if (!editing) {
      return $_("task.edit_task_page.prompt_description_creating")
    }
    if (task.requirements.length > 0) {
      return $_(
        "task.edit_task_page.prompt_description_editing_with_requirements",
      )
    }
    return $_("task.edit_task_page.prompt_description_editing_no_requirements")
  }
</script>

<div class="flex flex-col gap-2 w-full">
  <FormContainer
    submit_label={editing
      ? $_("task.edit_task_page.save_task")
      : $_("task.edit_task_page.create_task")}
    on:submit={create_task}
    bind:warn_before_unload
    bind:error
    bind:submitting
    bind:saved
  >
    <div>
      <div class="text-xl font-bold">
        {$_("task.edit_task_page.part_1_overview")}
      </div>
      {#if creating && !hide_example_task}
        <h3 class="text-sm mt-1">
          {$_("task.edit_task_page.just_exploring")}
          <button class="link text-primary" on:click={example_task}
            >{$_("task.edit_task_page.try_example")}</button
          >
        </h3>
      {/if}
    </div>
    <FormElement
      label={$_("task.edit_task_page.task_name_label")}
      id="task_name"
      description={$_("task.edit_task_page.task_name_description")}
      bind:value={task.name}
      max_length={120}
    />

    <FormElement
      label={$_("task.edit_task_page.prompt_task_instructions_label")}
      inputType="textarea"
      id="task_instructions"
      description={prompt_description()}
      bind:value={task.instruction}
    />

    <FormElement
      label={$_("task.edit_task_page.task_description_label")}
      inputType="textarea"
      id="task_description"
      description={$_("task.edit_task_page.task_description_description")}
      optional={true}
      bind:value={task.description}
    />

    <FormElement
      label={$_("task.edit_task_page.thinking_instructions_label")}
      inputType="textarea"
      id="thinking_instructions"
      optional={true}
      description={$_("task.edit_task_page.thinking_instructions_description")}
      info_description={$_("task.edit_task_page.thinking_instructions_info")}
      bind:value={task.thinking_instruction}
    />

    {#if show_requirements}
      <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
        <div class="text-xl font-bold" id="requirements_part">
          {$_("task.edit_task_page.part_2_requirements")}
        </div>
        <div class="text-xs text-gray-500">
          {$_("task.edit_task_page.requirements_description")}
          <a
            href="https://docs.getkiln.ai/docs/reviewing-and-rating"
            target="_blank"
            class="link">{$_("task.edit_task_page.learn_more")}</a
          >.
        </div>
      </div>

      <!-- Requirements Section -->
      <FormList
        content={task.requirements}
        content_label={$_("task.edit_task_page.requirement_label")}
        start_with_one={false}
        empty_content={{
          name: "",
          description: "",
          instructions: "",
          priority: 1,
        }}
        let:item_index
      >
        <div class="flex flex-col gap-3">
          <div class="flex flex-row gap-1">
            <div class="grow flex flex-col gap-1">
              <FormElement
                label={$_("task.edit_task_page.requirement_name_label")}
                info_description={$_(
                  "task.edit_task_page.requirement_name_info",
                )}
                id="requirement_name_{item_index}"
                light_label={true}
                bind:value={task.requirements[item_index].name}
                max_length={32}
              />
            </div>
            <div class="flex flex-col gap-1">
              <FormElement
                label={$_("task.edit_task_page.rating_type_label")}
                inputType="select"
                id="requirement_type_{item_index}"
                light_label={true}
                select_options={[
                  [
                    "five_star",
                    $_("task.edit_task_page.rating_types.five_star"),
                  ],
                  [
                    "pass_fail",
                    $_("task.edit_task_page.rating_types.pass_fail"),
                  ],
                  [
                    "pass_fail_critical",
                    $_("task.edit_task_page.rating_types.pass_fail_critical"),
                  ],
                ]}
                bind:value={task.requirements[item_index].type}
              />
            </div>
            <div class="flex flex-col gap-1">
              <FormElement
                label={$_("task.edit_task_page.priority_label")}
                inputType="select"
                id="requirement_priority_{item_index}"
                light_label={true}
                select_options={[
                  [0, $_("task.edit_task_page.priorities.p0_critical")],
                  [1, $_("task.edit_task_page.priorities.p1_high")],
                  [2, $_("task.edit_task_page.priorities.p2_medium")],
                  [3, $_("task.edit_task_page.priorities.p3_low")],
                ]}
                bind:value={task.requirements[item_index].priority}
              />
            </div>
          </div>
          <div class="grow flex flex-col gap-1">
            <FormElement
              label={$_("task.edit_task_page.requirement_instructions_label")}
              info_description={$_(
                "task.edit_task_page.requirement_instructions_info",
              )}
              inputType="textarea"
              id="requirement_instructions_{item_index}"
              light_label={true}
              bind:value={task.requirements[item_index].instruction}
            />
          </div>
        </div>
      </FormList>
    {/if}

    <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
      <div class="text-xl font-bold">
        {$_("task.edit_task_page.part")}
        {show_requirements ? "3" : "2"}: {$_(
          "task.edit_task_page.input_schema_title",
        )}
      </div>
      <div class="text-xs text-gray-500">
        {$_("task.edit_task_page.input_schema_description")}
      </div>
    </div>

    <div>
      {#if editing}
        <div>
          <div class="text-sm mb-2 flex flex-col gap-1">
            <p>
              {$_("task.edit_task_page.cannot_edit_existing_schema", {
                values: {
                  type: $_(
                    "task.edit_task_page.input_schema_title",
                  ).toLowerCase(),
                },
              })}
            </p>
            <p>
              {$_("task.edit_task_page.clone_task_instead")}
              <a
                class="link"
                href="/settings/clone_task/{target_project_id}/{task.id}"
                >{$_("task.edit_task_page.clone_this_task")}</a
              >
              {$_("task.edit_task_page.instead")}
            </p>
          </div>
          <Output
            raw_output={task.input_json_schema ||
              $_("task.edit_task_page.input_format_plain_text")}
          />
        </div>
      {:else}
        <SchemaSection
          bind:this={inputSchemaSection}
          bind:schema_string={task.input_json_schema}
        />
      {/if}
    </div>

    <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
      <div class="text-xl font-bold">
        {$_("task.edit_task_page.part")}
        {show_requirements ? "4" : "3"}: {$_(
          "task.edit_task_page.output_schema_title",
        )}
      </div>
      <div class="text-xs text-gray-500">
        {$_("task.edit_task_page.output_schema_description")}
      </div>
    </div>

    <div>
      {#if editing}
        <div>
          <div class="text-sm mb-2 flex flex-col gap-1">
            <p>
              {$_("task.edit_task_page.cannot_edit_existing_schema", {
                values: {
                  type: $_(
                    "task.edit_task_page.output_schema_title",
                  ).toLowerCase(),
                },
              })}
            </p>
            <p>
              {$_("task.edit_task_page.clone_task_instead")}
              <a
                class="link"
                href="/settings/clone_task/{target_project_id}/{task.id}"
                >{$_("task.edit_task_page.clone_this_task")}</a
              >
              {$_("task.edit_task_page.instead")}
            </p>
          </div>
          <Output
            raw_output={task.output_json_schema ||
              $_("task.edit_task_page.output_format_plain_text")}
          />
        </div>
      {:else}
        <SchemaSection
          bind:this={outputSchemaSection}
          bind:schema_string={task.output_json_schema}
        />
      {/if}
    </div>
  </FormContainer>
</div>
