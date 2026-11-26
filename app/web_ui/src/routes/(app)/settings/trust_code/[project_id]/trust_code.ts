import { client } from "$lib/api_client"
import { addCodeTrust, checkAddCodeTrust } from "$lib/api/v2_eval_api"
import { createKilnError, type KilnError } from "$lib/utils/error_handlers"

export type TrustCodeState =
  | { kind: "loading" }
  | { kind: "question"; project_name: string }
  | { kind: "trusted"; project_name: string }
  | { kind: "error"; error: KilnError }

async function load_project_name(project_id: string): Promise<string> {
  const { data, error } = await client.GET("/api/projects/{project_id}", {
    params: { path: { project_id } },
  })
  if (error) {
    throw error
  }
  return data.name
}

/** The page's first state: the trust question, or trusted when trust was already granted. */
export async function load_trust_code(
  project_id: string,
): Promise<TrustCodeState> {
  try {
    const [project_name, trust] = await Promise.all([
      load_project_name(project_id),
      checkAddCodeTrust(project_id),
    ])
    return { kind: trust.trusted ? "trusted" : "question", project_name }
  } catch (e) {
    return { kind: "error", error: createKilnError(e) }
  }
}

/** Grants code trust for this app session. Returns the error, or null on success. */
export async function grant_code_trust(
  project_id: string,
): Promise<KilnError | null> {
  try {
    await addCodeTrust(project_id)
    return null
  } catch (e) {
    return createKilnError(e)
  }
}
