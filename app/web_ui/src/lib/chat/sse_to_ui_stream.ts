import { EventSourceParserStream } from "@ai-sdk/provider-utils"
import type { UIMessageChunk } from "ai"

const SSE_DONE = "[DONE]"

/**
 * Converts an SSE Response body to a ReadableStream of UIMessageChunk.
 * Compatible with AI SDK data stream protocol (x-vercel-ai-ui-message-stream: v1).
 */
export function sseToUIMessageChunkStream(
  body: ReadableStream<Uint8Array>,
): ReadableStream<UIMessageChunk> {
  const eventStream = body
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- TextDecoderStream type mismatch with ReadableStream
    .pipeThrough(new TextDecoderStream() as any)
    .pipeThrough(new EventSourceParserStream())

  return eventStream.pipeThrough(
    new TransformStream({
      transform(msg, controller) {
        if (msg.data?.trim() && msg.data.trim() !== SSE_DONE) {
          try {
            controller.enqueue(JSON.parse(msg.data) as UIMessageChunk)
          } catch {
            // Skip non-JSON
          }
        }
      },
    }),
  )
}
