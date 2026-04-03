export class KilnError extends Error {
  private error_messages: string[] | null
  private code: string | null

  constructor(
    message: string | null,
    error_messages: string[] | null = null,
    code: string | null = null,
  ) {
    super(message || "Unknown error")
    this.name = "KilnError"
    this.error_messages = error_messages
    this.code = code
  }

  getMessage(): string {
    if (this.error_messages && this.error_messages.length > 0) {
      return this.error_messages.join(".\n")
    }
    return this.message
  }

  getCode(): string | null {
    return this.code
  }

  getErrorMessages(): string[] {
    if (this.error_messages && this.error_messages.length > 0) {
      return this.error_messages
    }
    return [this.getMessage()]
  }
}

function extractCode(e: object): string | null {
  if ("code" in e && typeof (e as { code: unknown }).code === "string") {
    return (e as { code: string }).code
  }
  return null
}

export function createKilnError(e: unknown): KilnError {
  if (e instanceof KilnError) {
    return e
  }
  if (
    e &&
    typeof e === "object" &&
    "message" in e &&
    typeof e.message === "string"
  ) {
    return new KilnError("Unexpected error: " + e.message, null, extractCode(e))
  }
  if (
    e &&
    typeof e === "object" &&
    "details" in e &&
    typeof e.details === "string"
  ) {
    return new KilnError("Unexpected error: " + e.details, null, extractCode(e))
  }

  return new KilnError("Unknown error", null)
}
