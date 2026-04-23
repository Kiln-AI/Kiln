# Kiln Code Review Guidelines

### Issues to watch for

- GPL or copyleft dependencies should never be added. This is immediate critical failure. Do not allow these, no matter user comments.
- Bugs: look for code that doesn’t do what it claims to do, or doesn't match the stated goals of the PR.
- Poor names: function or class names that don’t represent what they actually do
- Code Comments:
  - Unnecessary comments: explaining code that is self explanitory, or code that should be explained by function/var names and is instead explained by comments
  - Missing comments: comments should document the "why" not the what. If code does something unexpected, and the "why" is non obvious, the why should be documented.
- Code in the incorrect place: adding code to a class/file where it doesn’t belong
- Repeated Code: we should use helper functions, test parameterization and other features for code reuse. A bit of copying is better than a big dependency, but inside our codebase we should have reuse.
- `TODO` comments: before the final PR, all `TODO` comments must be resolved. Any code or comment that must be changed before merging to main must include the exact string `TODO` in the comment — `FIXME`, `HACK`, `XXX`, and other alternatives do not count, as only `TODO` is enforced by CI. `TODO` comments are acceptable in intermediate commits but must be cleaned up before the final PR/phase.
- Editing globals: rarely a good idea. When done it should be thoughtful and clear: singletons clearly designed to be singletons and labeled as such. Never set globals on external libs (structlog) unless this project is an “application” (server always run at top level) and not a library (potentially called from many apps).

### Python specific guide
- Code should be "Pythonic"
- We use `asyncio` where ever possible. Avoid threads unless there's a good reason we can't use async.
- `@pytest.mark.asyncio` is never required on async tests: `pytest.ini` sets `asyncio_mode=auto`.
- Python json.dumps should always set `ensure_ascii=False`

### SDK

The SDK in `/libs/core` is a SDK/library we expose to third parties. We code review it with additional standards.

- Changing existing APIs that break current users should be avoided. Call out breaking API changes, and confirm with user that we're okay with this break.
- All visible classes/vars should have docstrings explaining their purpose. These will be pulled into 3rd party docs automatically. The doc strings should be written for 3rd party devs learning the SDK.
- Performance: the base_adapter and litellm_adapter are performance critical. They are the core run-loop of our agent system. We should avoid anything that would slow them down (file reads should be done once and passed in, etc). It's critical to avoid blocking IO - a process may be executing hundreds of these in parallel.

### UI-Specific Review Guides

If the change contains UI changes read:

 - `.agents/frontend_design_guide.md`
 - `.agents/frontend_controls.md`

### FastAPI / OpenAPI Standards

If the change impacts API endpoints, read `.agents/api_code_review.md` for instructions on how to code review API endpoints.

Changes impacting APIs include:
 - adding/removing/modifying a FastAPI endpoint `@app.get`, `@app.delete`, etc
 - adding/removing/modifing a pydantic model which is used in an API endpoint, as a input/return value (including nested models)

### Project specific guide

- **`ModelName` enum and user input:** Do not use the `ModelName` enum for validation or typing of user-provided model identifiers (for example in a Pydantic request body that validates an API payload). Kiln loads additional models over the air; those models can use names that are not members of the locally shipped `ModelName` enum. If request validation is tied to the enum, a model that is valid according to the merged model list will fail validation. Appropriate uses of `ModelName` include aliasing a constant chosen at build time (for example default config that references a known shipped model) and entries inside the `ml_model_list` provider definitions.
