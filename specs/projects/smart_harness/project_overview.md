---
status: draft
---

# Kiln Smart Harness

This is a design project to update the Kiln harness for the next level of optimization we want to perform.

Some quick examples of "the next level of optimization":

- Jev/decision model routing: pick the model for the next turn based on Jev. Hard problem = smart model. Easy problem = cheap model.
- Jev/decision based "quick answers"/"decision tree"
  - Are they asking for hours of operation? Just answer without an LLM. It's easy.

## Examples of "the next level of optimization"

This list is not complete, but it's good for testing designs.

- First turn call: always call the "get_user_info" tool
  - No LLM call for something we always want. It's silly to put a rule in the prompt ("always call get_user_info") and spend decode time on this. It should be code/config/rule.
- Model routing: call a decision model to ask "which model and thinking level should we use", then call the LLM step, potentially overriding the defaults.
- Canned responses
  - Call a decision model like Jev: "Can we use one of our pre-canned responses, or should we call the LLM?"
    - "Is the user asking about hours of operation, and is the canned response a good response?"
    - "Did the user send a general welcome message like 'hello' or 'yo' or 'who are u', and should we respond with our general greeting explaining what to do?"
    - "Was the user's message clearly interrupted, and should we ask them to continue?"
    - etc.
    - "We should just call the LLM and let it handle this; our canned answers aren't appropriate, or this requires deeper reasoning."
- Decision trees: decision model calls (like Jev) forming a tree
  - Level 0: "Should we call the 'easy_answer' decision model to see if we can reply with one of our top 25 canned answers? Topics include hours of operation, general greeting, general capabilities question. Do not call if the message clearly requires analysis or reasoning, or combines several questions (canned responses are always a single question)."
  - Level 1: "Which subtree should we call? Is it an agent capability question, a question about the business (pricing, history), a question about privacy, a question about security, etc.?"
  - Level 2: a series of decision models
    - The capability one can choose between 25 capability answers (or "none fit")
    - The privacy one can choose between 12 privacy answers (or "none fit")
    - etc.
- Real logic: an advanced example. The functions/returns are not well formed at all, but you get the idea.

```
def custom_middleware(inputs, next_level, options)
  if turn_number==1
    return {tool_call:get_user_info}

  # see above
  canned_response, canned_confidence = call_canned_response_decision_tree(input)

  # asks decision model
  needs_smarter_model =

  if canned_response is not None && canned_confidence > 0.9 && needs_smarter_model < 0.5
    return canned_response

  new_options = options
  if needs_smarter_model > 0.5
    return next(inputs, next_level, options.merge({model_override: opus, thinking_level_override: xhigh}))
    # ALT VERSION: return {model_override: opus, thinking_level_override: xhigh}

  # keep defaults by not returning overrides
  return next(inputs, next_level)
```

## Technical Design: Middleware?

- Is this best as a "middleware" abstraction? The same as HTTP and other agent stacks do? Think FastAPI/Starlette/go-http/etc.
- Come up with some sort of clean middleware interface. It:
  - Can return instantly, bypassing the LLM entirely, e.g. `return {tool_call:get_user_info}`
  - Can redirect to a subagent (P2)
  - Can return overrides (thinking level, model, hyperparameters). The normal flow is called, but with settings tweaked.
  - Can look at a tool response and change it. E.g.: a tool returning 300k tokens… return an error instead. Note: this can be achieved today through tool call wrappers, but not for LLM responses.
  - Can do nothing: just pass through.
- Both "code middleware" and "decision model middleware" make sense for sure.
  - What about LLM middleware? We shouldn't rule out using an LLM for making these same routing decisions. The design should support it, but doing it should be pretty rare. Still, an LLM with light reasoning and a long cached prompt could be great for routing. Why? Reasoning lets it top decision models, prompt caching makes it cheaper than letting the main model reason about calling a subagent, and reasoning is kept out of the core model's trace, keeping that shorter.
- Stacked: middleware APIs in HTTP are nice because they can be stacked. It would be nice to have that property:
  - The run config gets a list of middleware, not one.
  - HTTP examples of the concept: stack all of these
    - Check rate limit middleware
    - Check auth middleware
    - Check response doesn't contain secrets middleware
  - Example for an agent: collapse the complex `custom_middleware` above into a stack.
    - 1: First turn? Return the get_user_info tool call.
    - 2: Canned answer works?
    - 3: Needs thinking overrides?
    - Not perfect, as it can't do `canned_confidence > 0.9 && needs_smarter_model < 0.5`, but that was me adding complexity for the sake of it. A code middleware should be able to call others if we want to build more complex logic (the way code tools can call other tools).
- Big question: does the "middleware" data model just point to a task?
  - It could point to a task (see "Can a middleware be composed of existing Kiln components?").
  - It could optionally add "filters" (`turn_number==1`), or those could be in code only?

### Can a middleware be composed of existing Kiln components, and should it?

- LLM and decision models: could just be Kiln tasks.
  - The task would need to implement a specific response schema of "middleware" (see above).
  - Really nice because our work to make tool responses work across many forms (JSON mode, JSON instructions, JSON schema, decision models, etc.) just works.
  - Really nice because we can write evals and optimize them, as they are just tasks.
  - Sub-agents already do this pattern: sub-agents aren't anything new, they're a tool -> task wrapper.
- Code:
  - Not as clean, as we don't have "code tasks" today.
  - We have "code tools" today: the sandbox, versioning, etc.
  - It might be the right call to add "code tasks", reusing infra from code tools. Then we could keep "a middleware can be any task conforming to the middleware schema".

The big win is that Kiln is designed to optimize and evaluate tasks, so you get the chance to optimize and evaluate middleware. Now: should that ever be done on just a middleware and not the whole agent? Hard to say. The optimizer looking at the top level could add/remove/change middleware.
