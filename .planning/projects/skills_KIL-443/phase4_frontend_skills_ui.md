# Phase 4: Frontend - Skills Management UI

## Goal

Create the Skills management pages: list, create, and detail/edit views. Follow the existing Intro → List → Create pattern used by tools and RAG configs.

## Route Structure

Under Settings, following the same project-level pattern as tools management:

```
app/web_ui/src/routes/(app)/settings/
  manage_skills/
    [project_id]/
      +page.svelte          # List page (intro if empty, table if skills exist)
      create/
        +page.svelte        # Create skill form
      [skill_id]/
        +page.svelte        # Detail/edit page
```

## Files to Create/Modify

### New: `app/web_ui/src/routes/(app)/settings/manage_skills/[project_id]/+page.svelte`

Skills list page. Shows an intro screen when no skills exist, a table when skills are present.

**Empty state**: Use `Intro` component with:

- Title: "Agent Skills"
- Description explaining what skills are and how they help agents
- Action button: "Create Skill" linking to create page

**List state**: Use `AppPage` with:

- Title: "Skills"
- Action button: "Create Skill"
- Table/list of skills showing: name, description, created date
- Each row links to the detail page

Pattern reference: Follow `settings/manage_tools/[project_id]/+page.svelte` closely.

```svelte
<script lang="ts">
  import AppPage from "$routes/(app)/app_page.svelte"
  import Intro from "$lib/ui/intro.svelte"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { onMount } from "svelte"

  $: project_id = $page.params.project_id

  let skills: Skill[] = []
  let loading = true

  onMount(async () => {
    const { data } = await client.GET("/api/projects/{project_id}/skills", {
      params: { path: { project_id } },
    })
    if (data) skills = data
    loading = false
  })
</script>

{#if !loading && skills.length === 0}
  <Intro
    title="Agent Skills"
    description={[
      "Skills are reusable instructions that help agents perform specific tasks.",
      "Create skills to give your agents domain knowledge, workflows, and guidelines.",
    ]}
    action_buttons={[
      { label: "Create Skill", href: `/settings/manage_skills/${project_id}/create` },
    ]}
  />
{:else}
  <AppPage
    title="Skills"
    action_buttons={[
      { label: "Create Skill", href: `/settings/manage_skills/${project_id}/create` },
    ]}
  >
    <!-- Table of skills -->
  </AppPage>
{/if}
```

### New: `app/web_ui/src/routes/(app)/settings/manage_skills/[project_id]/create/+page.svelte`

Create skill form using `FormContainer` and `FormElement`.

Fields:

- **Name** (`name`): text input with validation hint (lowercase, underscores only). FormElement with custom validation.
- **Description** (`description`): textarea, max 1024 chars. Hint about what makes a good description.
- **Instructions** (`body`): large textarea for the skill body content. This is the main skill content.

Pattern reference: Similar to the prompt create page or RAG config create.

```svelte
<script lang="ts">
  import AppPage from "$routes/(app)/app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"

  $: project_id = $page.params.project_id

  let name = ""
  let description = ""
  let body = ""

  async function handleSubmit() {
    const { data, error } = await client.POST(
      "/api/projects/{project_id}/skills",
      {
        params: { path: { project_id } },
        body: { name, description, body },
      }
    )
    if (data) {
      goto(`/settings/manage_skills/${project_id}`)
    }
  }
</script>

<AppPage
  title="Create Skill"
  subtitle="Create reusable instructions for your agents."
  back_button={{ label: "Skills", href: `/settings/manage_skills/${project_id}` }}
>
  <FormContainer submit_label="Create Skill" on:submit={handleSubmit}>
    <FormElement
      label="Name"
      info_description="Lowercase letters, numbers, and underscores only. E.g. 'code_review'"
      bind:value={name}
    />
    <FormElement
      label="Description"
      inputType="textarea"
      info_description="Describe what this skill does and when to use it. This helps agents decide when to load the skill."
      bind:value={description}
    />
    <FormElement
      label="Instructions"
      inputType="textarea"
      info_description="The main skill content. Write instructions, examples, and guidelines that will help the agent."
      bind:value={body}
    />
  </FormContainer>
</AppPage>
```

### New: `app/web_ui/src/routes/(app)/settings/manage_skills/[project_id]/[skill_id]/+page.svelte`

Detail/edit page for a single skill. Shows skill properties and allows editing.

Uses `AppPage` + `PropertyList` for display, `EditDialog` for editing fields.

Fields shown:

- Name (read-only after creation, since it's used for directory naming)
- Description (editable)
- Instructions/body (editable, large textarea)
- Created date (read-only)

### Modify: Settings page

Add a "Manage Skills" entry to the Settings hub page (`settings/+page.svelte`), following the same pattern as "Manage Tools".

### Modify: `app/web_ui/src/lib/types.ts`

Add TypeScript type re-exports for the Skill schema once the API schema is regenerated.

## Key Design Notes

- Skills are project-level (not task-level), living under Settings like tools management
- The `name` field validation should give clear feedback: show the snake_case rules, auto-suggest converting spaces to underscores
- The `body` (instructions) textarea should be generous in size — this is the main content authors will write
- After creating/editing a skill, the API schema needs to be regenerated (`generate_schema.sh`)
