import { _ } from "svelte-i18n"
import { get } from "svelte/store"

export class KilnError extends Error {
  private error_messages: string[] | null

  constructor(message: string | null, error_messages: string[] | null = null) {
    super(message || get(_)("errors.unknown_error"))
    this.name = get(_)("errors.kiln_error")
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
    return new KilnError(
      get(_)("errors.unexpected_error") + ": " + e.message,
      null,
    )
  }
  if (
    e &&
    typeof e === "object" &&
    "details" in e &&
    typeof e.details === "string"
  ) {
    return new KilnError(
      get(_)("errors.unexpected_error") + ": " + e.details,
      null,
    )
  }

  return new KilnError(get(_)("errors.unknown_error"), null)
}

// 便利函数：创建带翻译的常见错误
export function createTranslatedKilnError(
  errorKey: string,
  errorMessages: string[] | null = null,
): KilnError {
  return new KilnError(get(_)(`errors.${errorKey}`), errorMessages)
}

// 便利函数：创建带参数的翻译错误
export function createTranslatedKilnErrorWithParams(
  errorKey: string,
  params: Record<string, any>,
  errorMessages: string[] | null = null,
): KilnError {
  return new KilnError(
    get(_)(`errors.${errorKey}`, { values: params }),
    errorMessages,
  )
}
