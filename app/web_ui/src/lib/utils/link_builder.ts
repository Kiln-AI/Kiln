const FINE_TUNE_PROMPT_PREFIX = "fine_tune_prompt::"

export function prompt_link(
  project_id: string,
  task_id: string,
  prompt_id: string,
): string | undefined {
  if (!project_id || !task_id || !prompt_id) {
    return undefined
  }
  // Special case for fine-tuned prompts
  if (prompt_id.startsWith(FINE_TUNE_PROMPT_PREFIX)) {
    // Get the last component of the prompt ID. fine_tune_prompt::[project_id]::[task_id]::fine_tune_id
    const trimmed_prompt_id = prompt_id.replace(FINE_TUNE_PROMPT_PREFIX, "")
    const fine_tune_id =
      trimmed_prompt_id.split("::").pop() || trimmed_prompt_id
    return `/fine_tune/${project_id}/${task_id}/fine_tune/${encodeURIComponent(fine_tune_id)}`
  }
  if (!prompt_id.includes("::")) {
    // not an ID style prompt, link to static
    return `/prompts/${project_id}/${task_id}/generator_details/${encodeURIComponent(prompt_id)}`
  }
  // ID style prompt, link to saved
  return `/prompts/${project_id}/${task_id}/saved/${encodeURIComponent(prompt_id)}`
}
