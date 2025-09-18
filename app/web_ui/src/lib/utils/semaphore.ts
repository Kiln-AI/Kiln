export class Semaphore {
  private q: Array<() => void> = []
  private n: number

  constructor(max: number) {
    this.n = max
  }

  async acquire() {
    if (this.n > 0) {
      this.n--
      return
    }
    await new Promise<void>((res) => this.q.push(res))
  }

  release() {
    const next = this.q.shift()
    if (next) {
      next()
    } else {
      this.n++
    }
  }
}
