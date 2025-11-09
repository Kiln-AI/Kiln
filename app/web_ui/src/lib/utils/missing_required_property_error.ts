export class MissingRequiredPropertyError extends Error {
  constructor(
    msg: string,
    public source_path: string,
  ) {
    super(msg)
    this.name = "MissingRequiredPropertyError"
  }
}

export class IncompleteObjectError extends Error {
  constructor(
    msg: string,
    public source_path: string,
  ) {
    super(msg)
    this.name = "IncompleteObjectError"
  }
}
