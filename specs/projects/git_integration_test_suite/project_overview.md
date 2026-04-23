---
status: complete
---

The project is to create a git integration test suite for `specs/projects/git_auto_sync`. A test suite of all major flows, error cases, etc - using a real git repo.

However, I don't want the design docs to color the test suite creation so we're doing a clean-room setup. Your the first agent, who can read the docs and write the   
  "clean" spec. The goal is to describe the system by its goals and capabilities, without carrying over implementation details (which might be flawed). We need to explain the project goals, without explaining the implementation. You can read the `git_auto_sync` specs to write your spec, however, a clean agent will be launched to implement the tests and will only read your spec, not the `git_auto_sync` spec.
                        
Test Suite Setup:                                                                                                                                                                
- Separate from all other tests. This isn’t aware of or integrated with the unit tests from the main project - it’s a new separate integration suite. 
- Black box/clean room: built at the scenario level, not coloured by the design details.
  - Right level: needs to be aware that we use “stash” for clean state (to verify history is moved there), but not specifics of the order we call git commands in.
- Real git repos: use fixtures to create actual git repos in tmp folders. When necessary, make a local remote so you can check push/pull/etc. Should be a able to test fully, on real repos, without a remote git server.

Goal: test all flows to ensure we are building a robust
- Don’t lose data ever: 
  - even our “clean up” flows should leave history in stash. We never completely delete a file write, the end up in git history in remote, or stashed.
  - Arbitrary disk writes in project folder should be captures, even if done outside of our datamodel. No write in folder is ever just deleted/dropped.
- Don’t get into a state that requires manual fixing/conflict resolution.
  - A key goal is that the system tracks the remote closely, can can always get back to “in sync with remote, ready to write” state, no matter what happens locally. We should test various ways of breaking this guarantee, and prove it’s robust.
- All git conflict scenarios tested:
  - race conditions with remote
  - rebase errors
  - stash errors
  - what else?? This list isn’t comprehensive 
- Test our “dev mode” catches mistakes
  - verify writing in a GET request fails
  - Check other “dev mode” catches we spec, and ensure they are in test suite
- Test 2 levels:
  - directly test the “library mode”, acquiring the write lock and testing scenarios directly.
  - from Kiln API level (covering the middleware): same test cases, but run inside a kiln API call
  - Design question for architecture: can we use a `with` context and pytest params so ever test runs both modes? Would be nice to reuse code!
- Middleware integration tests:
  - I’m not sure if these are needed beyond the API level testing suggested above. Suggest what’s needed, if anything. May already be covered by existing project.

