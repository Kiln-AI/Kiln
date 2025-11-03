export class MissingRequiredPropertyError extends Error {
  constructor(msg?: string) {
    super(msg)
    this.name = "MissingRequiredPropertyError"
  }
}
