import { test, expect } from "@playwright/test"

/* @act
## Goals
Verify the ActRight + Playwright + MCP install is wired up correctly.
This test runs against a `data:` URL and does not require the user's app.

## Assertions
- The `data:` URL renders its inline content.
- Playwright can read text from the rendered page.
*/
test("act sanity: install verification", async ({ page }) => {
  await page.goto("data:text/html,<h1>ActRight OK</h1>")
  await expect(page.getByRole("heading", { name: "ActRight OK" })).toBeVisible()
})
