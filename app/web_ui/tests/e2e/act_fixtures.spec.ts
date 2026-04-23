import { test, expect } from "./fixtures"

/* @act
## Goals
Verify the `cleanBackend` fixture actually resets the app into a clean state: no
projects and no registration. With the backend clean, the root layout's setup check
must redirect the UI to the welcome page at /setup.

## Fixtures
- cleanBackend

## Assertions
- After navigating to /, the app redirects to /setup.
- The "Welcome to Kiln" heading is visible.
*/
test("cleanBackend fixture: app redirects to /setup welcome when empty", async ({
  cleanBackend,
  page,
}) => {
  void cleanBackend
  await page.goto("/")
  await page.waitForURL(/\/setup$/)
  await expect(
    page.getByRole("heading", { name: "Welcome to Kiln" }),
  ).toBeVisible()
})

/* @act
## Goals
Verify the `seededProject` fixture lands the app in the "has projects, pick a task"
state: with a project seeded but no ui_state priming, the root layout must redirect
to /setup/select_task (not /setup, because projects exist).

## Fixtures
- seededProject

## Assertions
- After navigating to /, the app redirects to /setup/select_task.
- The "Select a Task" heading is visible.
*/
test("seededProject fixture: app redirects to /setup/select_task when a project exists", async ({
  seededProject,
  page,
}) => {
  void seededProject
  await page.goto("/")
  await page.waitForURL(/\/setup\/select_task$/)
  await expect(
    page.getByRole("heading", { name: "Select a Task" }),
  ).toBeVisible()
})

/* @act
## Goals
Verify the `seededProjectWithTask` fixture primes ui_state so the task-selection
redirect is skipped. Without a registered user, the setup check then falls through
to the registration gate at /setup/select_account — proving ui_state priming worked
(no /setup/select_task redirect).

## Fixtures
- seededProjectWithTask

## Assertions
- After navigating to /, the app does NOT redirect to /setup/select_task.
- The app lands on /setup/select_account (registration wall) because no user is
  registered yet.
*/
test("seededProjectWithTask fixture: ui_state primed, lands past task selection", async ({
  seededProjectWithTask,
  page,
}) => {
  void seededProjectWithTask
  await page.goto("/")
  await page.waitForURL(/\/setup\/select_account/)
})

/* @act
## Goals
Verify the `registeredUser` fixture satisfies the root layout's registration gate:
when combined with `seededProjectWithTask`, navigating to / must NOT redirect to
/setup/select_account, and must land on the app home route (/run, per the home
redirect in (app)/+page.svelte).

## Fixtures
- registeredUser
- seededProjectWithTask

## Assertions
- After navigating to /, the app does NOT redirect to /setup/*.
- The final URL is /run (home redirect target).
*/
test("registeredUser fixture: app lands on /run, not on the registration gate", async ({
  registeredUser,
  seededProjectWithTask,
  page,
}) => {
  void registeredUser
  void seededProjectWithTask
  await page.goto("/")
  await page.waitForURL(/\/run$/)
})
