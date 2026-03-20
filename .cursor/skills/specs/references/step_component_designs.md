# Step: Component Designs

Per-component detailed designs when architecture.md alone isn't sufficient.

## When to Use

You decided during the architecture step that component designs are needed. This happens when:

- Architecture.md would be too long (>~300 lines of technical content)
- Individual components have enough internal complexity to warrant their own docs
- Clear separation of concerns would improve clarity

## What Each Component Doc Covers

For each component, create a doc covering:

### Purpose and Scope

- What does this component do?
- What's NOT part of its responsibility?

### Public Interface

Full function/method signatures with:
- Parameter types
- Return types
- Exception/error conditions

### Internal Design Approach

- Key algorithms
- Data flow
- State management approach
- Any non-trivial implementation details

### Dependencies

- What this component depends on
- What depends on this component

### Test Plan

Specific test cases by name and what they verify.

## File Structure

Create one file per component in `specs/projects/PROJECT_NAME/components/`:

```
specs/projects/PROJECT_NAME/components/
├── authentication.md
├── data_store.md
└── api_handler.md
```

Each file:

```markdown
---
status: draft
---

# Component: [Component Name]

## Purpose and Scope
[...]
```

## Review

After writing all component docs:

> Component designs written to `specs/projects/PROJECT_NAME/components/`:
> - [component1.md]
> - [component2.md]
> - [...]
>
> Ready to continue to implementation plan?

Quick review — no need for detailed back-and-forth unless the user has concerns.

## Completion

When user confirms, mark each component file as `status: complete`.
