# Step: Architecture

Write a technical architecture doc through iterative Q&A. This is where you solve the hard technical problems.

## Process

1. Read overview + functional spec (+ ui_design if present)
2. Ask technical questions
3. Draft `architecture.md`
4. Present for review
5. Iterate based on feedback
6. Confirm, mark `status: complete`

## What to Cover

### Data Model

- What are the main entities?
- How do they relate?
- How will data be stored?

### Component Breakdown

- What are the major classes/modules?
- What are their responsibilities?
- How do they interact?

### Public Interfaces

- Function signatures, API contracts
- Protocols/interfaces between components
- What are the boundaries?

### Design Patterns

- What patterns are we using and why?
- Framework and library choices with rationale

### Technical Challenges

- Identify anything non-trivial
- Design the solution NOW, not during coding
- Hard problems get solved here

### Error Handling Strategy

- How do errors propagate?
- What's recoverable vs. fatal?
- What's the logging approach?

### Testing Strategy

- What kinds of tests?
- What coverage targets?
- What frameworks?
- Test approach per component

## Depth Requirement

The architecture must be deep enough that no significant technical decisions remain for the coding agent.

- Classes, functions, overall flow — specified
- Key algorithms — designed
- Test cases — planned
- Key dependencies — chosen

The coding agent executes a well-defined plan. It doesn't design.

## 1-Phase vs 2-Phase Decision

Decide whether the project needs component designs (step 5) or if everything fits in architecture.md:

**Single file (architecture.md only) when:**
- Architecture doc would be under ~300 lines of technical content
- Components don't have enough internal complexity to warrant separate docs
- Project is small to medium sized

**Two-phase (architecture.md + components/) when:**
- Architecture doc would exceed ~300 lines
- Individual components have enough complexity for their own docs
- Project is large with many interacting parts

Both approaches expect the same level of technical detail. It's just a matter of organization.

Communicate this decision to the user:

> This project is [small/large] enough that I [recommend/will] use a [single architecture doc / architecture doc plus component designs]. Does that sound right?

## Pushback

→ Load [references/pushback.md](references/pushback.md) if not already loaded.

Challenge technical decisions:

- Overengineering: building more than needed
- Wrong tool for the job: framework/library doesn't fit the use case
- Patterns that hurt testability or maintainability
- Insufficient error handling
- Missing edge cases in the technical design
- Framework choices that don't fit the requirements

Also push back on functional requirements that add disproportionate technical complexity. You can offer alternatives that span both functional spec and architecture:

> The feature you described (X) adds significant technical complexity because [reasons]. A few alternatives:
> - **Option A:** [Simplified feature] — [benefit]
> - **Option B:** [Different approach] — [benefit]
> - **Option C:** Proceed as planned — accept the complexity

## Completion

Create `specs/projects/PROJECT_NAME/architecture.md`:

```markdown
---
status: draft
---

# Architecture: [Project Name]

[Organized sections covering the areas above]
```

Present for review. Iterate if needed. When user confirms, mark `status: complete`.
