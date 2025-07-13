<script lang="ts">
  import type { Task } from "$lib/types"
  import Output from "../../../../(app)/run/output.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import SchemaSection from "./schema_section.svelte"
  import {
    current_project,
    load_current_task,
    load_rating_options,
  } from "$lib/stores"
  import { goto } from "$app/navigation"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { ui_state, projects } from "$lib/stores"
  import { get } from "svelte/store"
  import { client } from "$lib/api_client"
  import { tick } from "svelte"

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
        "Project ID: " + target_project_id
    }
  }

  async function create_task() {
    try {
      saved = false
      if (!target_project_id) {
        error = new KilnError(
          "You must create a project before creating a task",
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
        throw new KilnError("Current project not found", null)
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
        current_task_rating_options: null,
      })
      saved = true

      // reload the current task to make sure changes propagate throughout the UI
      // e.g. the rating options
      await load_current_task(get(current_project))
      await load_rating_options()

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
      if (
        !confirm("This will replace your current task edits. Are you sure?")
      ) {
        return
      }
    }

    // @ts-expect-error This is a partial task, which is fine.
    task = {
      name: "Joke Generator",
      description: "An example task from the KilnAI team.",
      instruction:
        "Generate a joke, given a theme. The theme will be provided as a word or phrase as the input to the model. The assistant should output a joke that is funny and relevant to the theme. If a style is provided, the joke should be in that style. The output should include a setup and punchline.",
      requirements: [],
      input_json_schema: JSON.stringify({
        type: "object",
        properties: {
          joke_topic: {
            title: "Joke Topic",
            type: "string",
            description: "The topic of the joke.",
          },
          joke_style: {
            title: "Joke Style",
            type: "string",
            description:
              "The style of the joke, such as 'dad joke' or 'kids joke'.",
          },
        },
        required: ["joke_topic"],
      }),
      output_json_schema: JSON.stringify({
        type: "object",
        properties: {
          setup: {
            title: "setup",
            type: "string",
            description: "The setup to the joke",
          },
          punchline: {
            title: "punchline",
            type: "string",
            description: "The punchline to the joke",
          },
        },
        required: ["setup", "punchline"],
      }),
    }
  }

  function prompt_description() {
    if (!editing) {
      return "The prompt for the model to follow."
    }
    if (task.requirements.length > 0) {
      return "The base prompt used by prompt generators (Basic, Multi-shot, etc). The task requirements below are appended to this. You can create additional prompts in the 'Prompts' tab to compare prompt performance."
    }
    return "The base prompt used by prompt generators (Basic, Multi-shot, etc). You can create additional prompts in the 'Prompts' tab to compare prompt performance."
  }
</script>

<div class="flex flex-col gap-2 w-full">
  <FormContainer
    submit_label={editing ? "Save Task" : "Create Task"}
    on:submit={create_task}
    bind:warn_before_unload
    bind:error
    bind:submitting
    bind:saved
  >
    <div>
      <div class="text-xl font-bold">Part 1: Overview</div>
      {#if creating && !hide_example_task}
        <h3 class="text-sm mt-1">
          Just exploring?
          <button class="link text-primary" on:click={example_task}
            >Try an example.</button
          >
        </h3>
      {/if}
    </div>
    <FormElement
      label="Task Name"
      id="task_name"
      description="A description for you and your team, not used by the model."
      bind:value={task.name}
      max_length={120}
    />

    <FormElement
      label="Prompt / Task Instructions"
      inputType="textarea"
      id="task_instructions"
      description={prompt_description()}
      bind:value={task.instruction}
    />

    <FormElement
      label="Task Description"
      inputType="textarea"
      id="task_description"
      description="A description for you and your team, not used by the model."
      optional={true}
      bind:value={task.description}
    />

    <FormElement
      label="'Thinking' Instructions"
      inputType="textarea"
      id="thinking_instructions"
      optional={true}
      description="Instructions for how the model should 'think' about the task prior to answering. Used for chain of thought style prompting."
      info_description="Used when running a 'Chain of Thought' prompt. If left blank, a default 'think step by step' prompt will be used. Optionally customize this with your own instructions to better fit this task."
      bind:value={task.thinking_instruction}
    />

    {#if show_requirements}
      <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
        <div class="text-xl font-bold" id="requirements_part">
          Part 2: Requirements
        </div>
        <div class="text-xs text-gray-500">
          Define requirements you can use to rate the results of the model.
          These are used in the prompt, ratings, evals and training.
          <a
            href="https://docs.getkiln.ai/docs/reviewing-and-rating"
            target="_blank"
            class="link">Learn more</a
          >.
        </div>
      </div>

      <!-- Requirements Section -->
      <FormList
        content={task.requirements}
        content_label="Requirement"
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
                label="Requirement Name"
                info_description="A short name to uniquely identify the requirement. This will appear in the rating UI. It's not used by the model."
                id="requirement_name_{item_index}"
                light_label={true}
                bind:value={task.requirements[item_index].name}
                max_length={32}
              />
            </div>
            <div class="flex flex-col gap-1">
              <FormElement
                label="Rating Type"
                inputType="select"
                id="requirement_type_{item_index}"
                light_label={true}
                select_options={[
                  ["five_star", "5 Star"],
                  ["pass_fail", "Pass / Fail"],
                  ["pass_fail_critical", "Pass / Fail / Critical"],
                ]}
                bind:value={task.requirements[item_index].type}
              />
            </div>
            <div class="flex flex-col gap-1">
              <FormElement
                label="Priority"
                inputType="select"
                id="requirement_priority_{item_index}"
                light_label={true}
                select_options={[
                  [0, "P0 - Critical"],
                  [1, "P1 - High"],
                  [2, "P2 - Medium"],
                  [3, "P3 - Low"],
                ]}
                bind:value={task.requirements[item_index].priority}
              />
            </div>
          </div>
          <div class="grow flex flex-col gap-1">
            <FormElement
              label="Instructions: a few sentences describing this requirement for the model"
              info_description="These instructions will be appended to the prompt and using during evals. It should be written with the model in mind. Example requirement: Name='Be Succinct' and Instruction='Use short sentences and simple language. Don't repeat yourself.'"
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
        Part {show_requirements ? "3" : "2"}: Input Schema
      </div>
      <div class="text-xs text-gray-500">
        What kind of input will the model receive?
      </div>
    </div>

    <div>
      {#if editing}
        <div>
          <div class="text-sm mb-2 flex flex-col gap-1">
            <p>
              You can't edit an existing task's input format, as existing
              dataset items would not conform to the new schema.
            </p>
            <p>
              You can
              <a
                class="link"
                href="/settings/clone_task/{target_project_id}/{task.id}"
                >clone this task</a
              >
              instead.
            </p>
          </div>
          <Output
            raw_output={task.input_json_schema || "Input Format: Plain text"}
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
        Part {show_requirements ? "4" : "3"}: Output Schema
      </div>
      <div class="text-xs text-gray-500">
        What kind of output will the model produce?
      </div>
    </div>

    <div>
      {#if editing}
        <div>
          <div class="text-sm mb-2 flex flex-col gap-1">
            <p>
              You can't edit an existing task's output format, as existing
              dataset items would not conform to the new schema.
            </p>
            <p>
              You can
              <a
                class="link"
                href="/settings/clone_task/{target_project_id}/{task.id}"
                >clone this task</a
              >
              instead.
            </p>
          </div>
          <Output
            raw_output={task.output_json_schema || "Output Format: Plain text"}
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
