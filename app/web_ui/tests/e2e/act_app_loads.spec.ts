import { test, expect } from "@playwright/test"

/* @act
## Goals
Verify the full stack is wired up: Playwright can launch the backend (FastAPI on 6535)
and the Vite dev server (on 6534), navigate to `/`, and receive a rendered page from
the Kiln web UI.

## Assertions
- The page at `/` responds and sets the title to something containing "Kiln"
  (the app uses VITE_BRANCH_NAME || "Kiln" as its title).
*/
test("act app loads: the Kiln web UI serves /", async ({ page }) => {
  await page.goto("/")
  await expect(page).toHaveTitle(/Kiln/)
})
