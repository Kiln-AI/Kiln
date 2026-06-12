/**
 * Compile-time exhaustiveness check for discriminated unions and enums.
 *
 * Place `assertNever(x)` in the `default` branch of a switch/if-else chain.
 * If all cases are handled the call is unreachable and TS is happy;
 * if a case is missing TS reports a type error at compile time.
 *
 * At runtime (should be unreachable), it throws for safety.
 */
export function assertNever(x: never): never {
  throw new Error(`Unexpected value: ${String(x)}`)
}
