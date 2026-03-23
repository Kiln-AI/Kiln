# Step: Functional Spec

Write a functional specification through iterative Q&A with the user.

## Process

1. Read the project overview
2. Identify gaps — what information is missing to fully specify what's being built
3. Ask clarifying questions in rounds:
   - Start with high-level questions
   - Then drill into details
   - You may need multiple rounds of Q&A
4. Draft `functional_spec.md` based on answers
5. Present for review
6. Iterate based on feedback
7. Confirm with user, mark `status: complete`

## What to Cover

The sections should adapt to the project. Here are common areas — include what's relevant, don't force a rigid template:

### Features and Behavior

- What does this thing do?
- What are the user flows or usage patterns?
- What are the key features?
- What's explicitly out of scope?

### Edge Cases and Error Handling

- What happens when things go wrong?
- What are the boundaries?
- How should errors be presented to users?
- What's recoverable vs. fatal?

### Input/Output Contracts

For APIs, CLIs, libraries:

- What goes in? Formats, validation requirements
- What comes out? Response formats, return types
- What are the contracts?

For APIs: endpoint definitions, request/response schemas
For CLIs: command structure, argument formats
For libraries: public interface, function signatures

### Configuration and Defaults

- What's configurable?
- What are sensible defaults?
- Where does configuration live?

### Constraints

- Performance requirements
- Compatibility requirements
- Security considerations
- Resource limits

### UI Projects Only

High-level screens/views and navigation at the functional level:

- What are the main screens/views?
- How do users navigate between them?
- What actions are available on each?

(Details will be in step 3: UI Design)

## Quality Bar

The spec should be complete enough that someone unfamiliar with the project could understand what is being built and why, from this document alone.

Every behavior and decision should be explicit. Don't leave gaps for the coder to fill in during implementation.

If you're unsure about something, ask. Don't guess.

## Pushback

→ Load [references/pushback.md](references/pushback.md) if not already loaded.

After drafting the spec, review it and challenge:

- Feature decisions that seem unnecessary or over-scoped
- Missing edge cases that will bite later
- Unclear or ambiguous requirements
- Scope that doesn't match the stated goals
- Requirements that add disproportionate complexity

Present concerns to the user with alternatives.

## Completion

Create `specs/projects/PROJECT_NAME/functional_spec.md`:

```markdown
---
status: draft
---

# Functional Spec: [Project Name]

[Organized sections covering the areas above]
```

Present for review. Iterate if needed. When user confirms, mark `status: complete`.
