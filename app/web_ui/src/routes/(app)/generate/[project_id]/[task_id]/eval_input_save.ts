import { client } from "$lib/api_client"
import { KilnError } from "$lib/utils/error_handlers"

// Saving a generated case to a split that holds eval inputs, for both generation flows.
//
// An eval input carries the case only: the eval runner produces an output per run config at
// eval time, so nothing is run here. The session tag is applied by this client because the
// eval-inputs endpoint, unlike the run endpoints, tags nothing itself.

// The case's text, as an eval input stores it. A task with an input schema has its input as a
// JSON string, the shape the eval builder mints its cases in too.
export function eval_input_text(
  input: string | Record<string, unknown>,
): string {
  return typeof input === "string" ? input : JSON.stringify(input)
}

// Whether a case dealt this split goes to the eval's inputs rather than the dataset. The
// eval names those splits; a tag it doesn't name is a dataset tag like any other.
export function is_eval_input_split(
  split_tag: string | null | undefined,
  eval_input_splits: string[] | null | undefined,
): boolean {
  return !!split_tag && !!eval_input_splits?.includes(split_tag)
}

// The same tags the run endpoints put on a generated run, in the same order, so a case is
// tagged the same way whichever store it lands in.
export function eval_input_tags(
  split_tag: string,
  session_id: string | null,
): string[] {
  const tags = ["synthetic"]
  if (session_id) {
    tags.push(`synthetic_session_${session_id}`)
  }
  tags.push(split_tag)
  return tags
}

// Saves one case as an eval input, returning its id. Throws on a failed save, like the run
// save it stands in for.
export async function save_eval_input(
  project_id: string,
  task_id: string,
  input: string | Record<string, unknown>,
  split_tag: string,
  session_id: string | null,
): Promise<string> {
  const { data, error } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/eval_inputs",
    {
      params: { path: { project_id, task_id } },
      body: {
        data: {
          type: "single_turn",
          user_message: { text: eval_input_text(input) },
        },
        tags: eval_input_tags(split_tag, session_id),
      },
    },
  )
  if (error) {
    throw error
  }
  if (!data?.id) {
    throw new KilnError("Save failed: no id returned.", null)
  }
  return data.id
}
