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
      const creating = !task.id
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
      requirements: [
        {
          name: "Keep on topic",
          instruction:
            "Keep the joke on topic. If the user specifies a theme, the joke must be related to that theme.",
          priority: 1,
          type: "five_star",
        },
        {
          name: "Keep it clean",
          instruction:
            "Avoid any jokes that are offensive or inappropriate. Keep the joke clean and appropriate for all audiences.",
          priority: 2,
          type: "pass_fail",
        },
        {
          name: "Be funny",
          instruction:
            "Make the joke funny and engaging. It should be something that someone would want to tell to their friends. Something clever, not just a simple pun.",
          priority: 1,
          type: "five_star",
        },
      ],
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
</script>

<div class="flex flex-col gap-2 w-full">
  <FormContainer
    submit_label={task.id ? "Save Task" : "Create Task"}
    on:submit={create_task}
    bind:warn_before_unload
    bind:error
    bind:submitting
    bind:saved
  >
    <div>
      <div class="text-xl font-bold">Part 1: Overview</div>
      {#if !task.id && !hide_example_task}
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
      label="Task Description"
      inputType="textarea"
      id="task_description"
      description="A description for you and your team, not used by the model."
      optional={true}
      bind:value={task.description}
    />

    <FormElement
      label="Task Instructions"
      inputType="textarea"
      id="task_instructions"
      description="This will form the basis of the model's prompt. Keep this high level, and define any details in the 'Requirements' section below."
      bind:value={task.instruction}
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

    <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
      <div class="text-xl font-bold" id="requirements_part">
        Part 2: Requirements
      </div>
      <div class="text-xs text-gray-500">
        Define any requirements for the task. These will become part of the
        prompt, but are also broken out for model evals and training.
      </div>
    </div>

    <!-- Requirements Section -->
    <FormList
      content={task.requirements}
      content_label="Requirement"
      start_with_one={true}
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
            label="Instructions"
            inputType="textarea"
            id="requirement_instructions_{item_index}"
            light_label={true}
            bind:value={task.requirements[item_index].instruction}
          />
        </div>
      </div>
    </FormList>

    <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
      <div class="text-xl font-bold" id="requirements_part">
        Part 3: Input Schema
      </div>
      <div class="text-xs text-gray-500">
        What kind of input will the model receive?
      </div>
    </div>

    <div>
      {#if task.id}
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
      <div class="text-xl font-bold" id="requirements_part">
        Part 4: Output Schema
      </div>
      <div class="text-xs text-gray-500">
        What kind of output will the model produce?
      </div>
    </div>

    <div>
      {#if task.id}
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
