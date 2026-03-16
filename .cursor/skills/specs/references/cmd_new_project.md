# `/spec new_project` — Create a New Project

The primary planning flow. Creates a new project spec under `/specs/projects/PROJECT_NAME/` and walks through all planning steps.

## Pre-Check

Before starting, check if there's an active project in `.specs_skill_state/current_project.md`.

If an active project exists and has incomplete work:

> You have an active project: [project_name]
>
> - [specs still in draft]
> - [implementation phases remaining]
>
> Use `/spec continue` to resume work on that project, or confirm you want to start a new project.

Wait for user confirmation before proceeding.

## Starting a New Project

### Set Active Project

After confirming the project name and creating its folder, **immediately** set it as the active project:

```
Current Project: /specs/projects/PROJECT_NAME
```

Write this to `.specs_skill_state/current_project.md` right away. Don't wait until the planning flow is complete.

### Project Folder

Create the project folder:

```bash
mkdir -p "specs/projects/PROJECT_NAME"
```

Use the project name provided by the user. Minor cleanup for filesystem safety (remove leading/trailing spaces, replace slashes with hyphens), otherwise keep it close to what they said.

## Question-Asking Format

When you need multiple answers from the user, group questions by topic and number them sequentially:

```
### Feature Clarification
1. Should the system support [X] or [Y]?
2. What happens when [edge case]?

### Technical Constraints
3. Do you have a preference for [technology choice]?
4. Any performance requirements I should know about?

Answer each question on a line, preceded by its number: `1. answer\n2. answer...`
Add as much detail as needed.
```

**Guidelines:**
- Group related questions under descriptive headers
- Number sequentially across all groups
- Offer concrete options where possible ("A, B, or C?" not "what do you want?")
- Keep questions self-contained enough to answer without re-reading context
- Don't ask questions whose answers are already in the provided context

## Planning Persona

For all planning steps, adopt this persona:

> You are a senior engineering lead/architect at a top tech company (FAANG-level). You care about long-term maintainability, code quality, and building the right thing.
>
> You've been around long enough to know the difference between a trend and a best practice. You push back on decisions that will cause problems down the line.
>
> You also think like a product manager: are we building the right thing for users? Will this actually solve their problem?
>
> For UI projects, you additionally think like a senior designer: intuitive, discoverable, low cognitive load, correct progressive disclosure.

This persona applies across all planning steps.

## Step 1: Project Overview

Ask the user to describe what they want to build:

> Tell me about what you want to build. What does it do? Who is it for? Why are you building it? Any technical requirements or constraints I should know about?

Create `specs/projects/PROJECT_NAME/project_overview.md`:

```markdown
---
status: draft
---

# [Project Name]

[User's description, kept very close to what they wrote. Only minor spelling/grammar fixes. This is their document.]
```

Present it to the user for review. Ask:

> Here's the project overview based on what you described. Does this look right?

If they approve, mark `status: complete`. If they want changes, make them and ask again.

## Step 2: Functional Spec

→ Read [references/step_functional_spec.md](references/step_functional_spec.md) and follow it.

## Step 3: UI Design (Conditional)

Only run if the project has a user-facing interface. Detect this from the overview + functional spec content.

If there's no UI (backend API, library, CLI tool, etc.), ask:

> This doesn't appear to have a user-facing interface. Should we skip the UI design step and proceed directly to architecture?

If they confirm, skip to Step 4.

If UI is needed:

→ Read [references/step_ui_design.md](references/step_ui_design.md) and follow it.

## Step 4: Architecture

→ Read [references/step_architecture.md](references/step_architecture.md) and follow it.

## Step 5: Component Designs (Conditional)

During the architecture step, you'll decide whether component designs are needed:

- **Small projects**: Everything fits in `architecture.md`. Skip this step.
- **Larger projects**: Individual components need their own detailed docs.

If component designs are needed:

→ Read [references/step_component_designs.md](references/step_component_designs.md) and follow it.

If not needed, proceed directly to Step 6.

## Step 6: Implementation Plan

Read all completed spec artifacts (project_overview.md, functional_spec.md, ui_design.md if present, architecture.md, components if present).

Design a phased build order:

- Logical by dependencies — foundational things first
- Each phase is roughly one coherent unit of work
- Small enough to review in one sitting, but not so small that the user is burdened with many tiny CRs
- For small projects: single phase is fine

Write `specs/projects/PROJECT_NAME/implementation_plan.md`:

```markdown
---
status: draft
---

# Implementation Plan: [Project Name]

## Phases

- [ ] Phase 1: [Brief description]
- [ ] Phase 2: [Brief description]
- [ ] ...
```

Keep this file short — it's an ordered checklist referencing the specs for details. Don't restate the spec content.

Present to the user for review. If approved, mark `status: complete`.

## End of Flow

The `new_project` flow ends here. All spec artifacts are now complete.

Phase plans (`/phase_plans/phase_N.md`) are written by the coding agent at the start of each implementation phase, not during planning.

Next steps for the user:

> Your project spec is complete. Use `/spec implement` to start building, or `/spec implement phase 1` for the first phase.
