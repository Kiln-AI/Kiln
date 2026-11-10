import type { NamedResetKwargs } from "$lib/types"

// There's no OpenEnv docs page yet, so this links the tools docs.
export const OPENENV_DOCS_URL = "https://docs.kiln.tech/docs/tools-and-mcp"
export const SEAHAVEN_URL = "https://github.com/Kiln-AI/Seahaven"

/** Copy for the fields shared by Connect OpenEnv and the Edit OpenEnv dialog. */
export const OPENENV_SERVER_FIELDS = {
  name: { label: "Name", description: "A name to identify this OpenEnv." },
  description: {
    label: "Description",
    description: "A description of this OpenEnv for your reference.",
  },
  url: {
    label: "Server URL",
    description: "The URL of the OpenEnv server.",
    info_description:
      "Kiln connects to this server but never starts or stops it. Start the server before you connect.",
    placeholder: "http://127.0.0.1:8004",
  },
} as const

export type ResetKwargs = NonNullable<NamedResetKwargs["reset_kwargs"]>

export const RESET_ARGUMENTS_INVALID_JSON =
  "Reset arguments must be valid JSON."
export const RESET_ARGUMENTS_NOT_OBJECT =
  "Reset arguments must be a JSON object."

export function format_reset_arguments(
  reset_kwargs: ResetKwargs | null | undefined,
): string {
  return JSON.stringify(reset_kwargs ?? {}, null, 2)
}

export type ParsedResetArguments =
  | { reset_kwargs: ResetKwargs; error: null }
  | { reset_kwargs: null; error: string }

/** Parse the Reset Arguments editor's text. Blank text is an empty object. */
export function parse_reset_arguments(text: string): ParsedResetArguments {
  if (!text.trim()) {
    return { reset_kwargs: {}, error: null }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return { reset_kwargs: null, error: RESET_ARGUMENTS_INVALID_JSON }
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { reset_kwargs: null, error: RESET_ARGUMENTS_NOT_OBJECT }
  }
  return { reset_kwargs: parsed as ResetKwargs, error: null }
}
