# `/spec continue` — Resume Work

Resume work on the active project. The "what should I do next?" command.

## Process

### 1. Read State

Load `.specs_skill_state/current_project.md` to find the active project:

```
Current Project: /specs/projects/PROJECT_NAME
```

### 2. No Active Project

If no active project (file doesn't exist or is empty):

List available project directories under `/specs/projects/`:

> No active project found. Available projects:
> - [project1]
> - [project2]
> - [...]
>
> Which project would you like to work on?

Set the selected project as active and proceed to step 3.

### 3. Determine Current State

Check the frontmatter `status` on each artifact in dependency order:

```
project_overview.md → functional_spec.md → ui_design.md (if exists)
→ architecture.md → components/ (if exists) → implementation_plan.md
```

- **If any spec artifact is missing or `status: draft`**: Resume the `new_project` flow at the next incomplete step
- **If all specs are `complete`**: Implementation time

### 4. Routing Logic

**If in speccing phase (artifacts incomplete):**

> Project [PROJECT_NAME] — continuing with [next step name]:
>
> - [artifact_name.md] is [draft/missing]
> - [next steps]
>
> Proceeding with [step name]...

Load the corresponding step reference file (step_functional_spec.md, step_architecture.md, etc.) and proceed with that step.

**If all specs complete but phases remain:**

> Project [PROJECT_NAME] — all specs complete. Ready to implement:
>
> - [ ] Phase 1: [description]
> - [ ] Phase 2: [description]
> - [ ]
>
> Implement next phase only, or all remaining phases?

This routes to `/spec implement` behavior.

**If all phases complete:**

> Project [PROJECT_NAME] — all phases implemented!
>
> What would you like to do?
> - Start a new project: `/spec new_project`
> - Review code: `/spec cr`
> - Something else

### 5. Confirm

Always confirm before taking action:

> About to: [action description]
>
> Proceed?

Wait for user confirmation before executing.

## Notes

- This command is a router — it doesn't do the work itself, it determines what to do next and loads the appropriate reference
- State is read from artifact frontmatter, not from a separate tracking file
- If user manually edited files and states are inconsistent, surface that and ask how to resolve
