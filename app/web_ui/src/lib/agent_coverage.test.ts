import { describe, it, expect } from "vitest"
import * as fs from "fs"
import * as path from "path"

function findPageFiles(dir: string): string[] {
  const results: string[] = []
  const entries = fs.readdirSync(dir, { withFileTypes: true })
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      results.push(...findPageFiles(fullPath))
    } else if (entry.name === "+page.svelte") {
      results.push(fullPath)
    }
  }
  return results
}

describe("agentInfo coverage", () => {
  const routesDir = path.resolve(__dirname, "../routes")
  const pageFiles = findPageFiles(routesDir)

  it("should find page files", () => {
    expect(pageFiles.length).toBeGreaterThan(0)
  })

  it.each(pageFiles.map((f) => [path.relative(routesDir, f), f]))(
    "%s contains agentInfo.set or agentInfo.update",
    (_relativePath, filePath) => {
      const content = fs.readFileSync(filePath as string, "utf-8")
      const hasSet = content.includes("agentInfo.set(")
      const hasUpdate = content.includes("agentInfo.update(")
      expect(
        hasSet || hasUpdate,
        `${_relativePath} is missing an agentInfo.set() or agentInfo.update() call. This is required to inform our agent what this page is.`,
      ).toBe(true)
    },
  )
})
