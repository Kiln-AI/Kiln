// Kiln's built-in tool IDs, mirroring KilnBuiltInToolId on the server. They are not
// in the generated OpenAPI client (the API types them as plain tool ID strings), so
// they live here rather than being retyped at each use site.

// Calls a model with a rendered prompt. Callable from sandboxed user code only.
export const LLM_TOOL_ID = "kiln_tool::llm"

// Runs an LLM-as-judge call using the enclosing code judge's own score schema, so
// it is usable only from a code judge.
export const LLM_JUDGE_TOOL_ID = "kiln_tool::llm_judge"
