export class KilnError extends Error {
  private error_messages: string[] | null

  constructor(message: string | null, error_messages: string[] | null = null) {
    super(message || "Unknown error")
    this.name = "KilnError"
    this.error_messages = error_messages
  }

  getMessage(): string {
    if (this.error_messages && this.error_messages.length > 0) {
      return this.error_messages.join(".\n")
    }
    return this.message
  }

  getErrorMessages(): string[] {
    if (this.error_messages && this.error_messages.length > 0) {
      return this.error_messages
    }
    return [this.getMessage()]
  }
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
    return new KilnError("Unexpected error: " + e.message, null)
  }
  if (
    e &&
    typeof e === "object" &&
    "details" in e &&
    typeof e.details === "string"
  ) {
    return new KilnError("Unexpected error: " + e.details, null)
  }
  if (
    e &&
    typeof e === "object" &&
    "message" in e &&
    typeof e.message === "string"
  ) {
    return new KilnError("Unexpected error: " + e.message, null)
  }

  return new KilnError("Unknown error", null)
}
