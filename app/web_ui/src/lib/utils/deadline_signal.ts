// Compose a user-driven abort signal with a hard deadline, keeping the two
// causes distinguishable after the fact. Callers race an interactive request
// against a fallback: a fired deadline means "give up and degrade
// gracefully", while a user abort must still cancel the whole flow — so the
// catch block needs to know which one rejected the request.
export type DeadlineSignal = {
  signal: AbortSignal
  // True iff the deadline fired and the user signal did not. A user abort
  // wins any race — checking the user signal keeps a simultaneous firing
  // from masking an explicit cancel as a mere timeout.
  timed_out: () => boolean
}

export function with_deadline(
  user_signal: AbortSignal,
  timeout_ms: number,
): DeadlineSignal {
  const deadline = AbortSignal.timeout(timeout_ms)
  return {
    signal: AbortSignal.any([user_signal, deadline]),
    timed_out: () => deadline.aborted && !user_signal.aborted,
  }
}
