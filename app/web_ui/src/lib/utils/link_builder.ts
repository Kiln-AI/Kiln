export function prompt_link(
  project_id: string,
  task_id: string,
  prompt_id: string,
): string | undefined {
  if (!project_id || !task_id || !prompt_id) {
    return undefined
  }
  if (!prompt_id.includes("::")) {
    // not an ID style prompt, link to static
    return `/prompts/${project_id}/${task_id}/generator_details/${encodeURIComponent(prompt_id)}`
  }
  // ID style prompt, link to saved
  return `/prompts/${project_id}/${task_id}/saved/${encodeURIComponent(prompt_id)}`
}
