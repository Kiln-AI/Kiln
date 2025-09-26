export function createLimiter(max: number) {
  let active = 0
  const queue: Array<{
    fn: () => Promise<unknown>
    resolve: (value: unknown) => void
    reject: (reason?: unknown) => void
  }> = []

  function next() {
    if (queue.length === 0 || active >= max) return
    active++
    const { fn, resolve, reject } = queue.shift()!

    fn()
      .then(resolve, reject)
      .finally(() => {
        active--
        next()
      })
  }

  return function run<T>(fn: () => Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      queue.push({
        fn: fn as () => Promise<unknown>,
        resolve: resolve as (value: unknown) => void,
        reject: reject as (reason?: unknown) => void,
      })
      next()
    })
  }
}
