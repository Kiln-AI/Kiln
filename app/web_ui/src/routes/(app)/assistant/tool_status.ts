import { isToolOutputError } from "$lib/chat/streaming_chat"

export type ToolStatusVariant =
  | "fetching"
  | "fetched"
  | "fetch_failed"
  | "saving"
  | "saved"
  | "save_failed"

/**
 * The status row for a tool part. A tool is in progress while its message is
 * still streaming and it has no output yet; after that it is done, or failed
 * when its output is an error.
 */
export function toolStatusVariant(
  output: unknown,
  isGet: boolean,
  isActiveMessage: boolean,
): ToolStatusVariant {
  if (output === undefined && isActiveMessage) {
    return isGet ? "fetching" : "saving"
  }
  if (isToolOutputError(output)) {
    return isGet ? "fetch_failed" : "save_failed"
  }
  return isGet ? "fetched" : "saved"
}
