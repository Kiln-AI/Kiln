---
status: complete
---

# Harness Tuner in Kiln

Move harness-tuner into the Kiln repository, give MCP connections roles, and put harness-tuner's agents on Kiln's own MCP server and skill.

This spec replaces [harness_tuner_switchover](../harness_tuner_switchover/project_overview.md), which kept harness-tuner in its own repository with its own gateway. It takes up the plan to limit MCP connections from [harness_tuner_port](../harness_tuner_port/project_overview.md), which was canceled. The MCP server itself, [kiln_mcp_server](../kiln_mcp_server/project_overview.md), is merged to main and live.

## Why

- **Two repositories.** Harness-tuner holds copies of things Kiln owns, and the two need machinery to stay in step: version checks both ways, a contract test, and a reader of Kiln's skill over MCP.
- **Two tool surfaces.** Harness-tuner's agents use its gateway, with tools of its own. Kiln's knowledge names Kiln's endpoints. So every endpoint needs a second name and a table between the two.
- **No protection for other MCP clients.** A chat client on Kiln's MCP server can read val and test data today. Only the skill's text tells it not to.
- **A second install.** A Kiln user must install a separate project to use harness-tuner.

## The end state

- **One repository and one release.** Harness-tuner ships with the Kiln app. The PyPI package `harness-tuner` stays, as a thin launcher of Kiln's copy.
- **One skill.** Harness-tuner's role procedures are in Kiln's skill, beside the knowledge they use.
- **One API and one MCP server.** Harness-tuner's agents get the same two tools as every MCP client: `call_kiln_api` and `kiln_skill`.
- **One fence.** A role on the MCP connection, enforced in Kiln's API. Every MCP client has one.

Harness-tuner's own Python code is trusted. It calls Kiln with no role and keeps val and test data away from its agents itself, as it does today. The roles are for agents. Its code keeps its structure: the move rewrites as little of it as possible.

## Principles

- **The REST API does not change by default.** A request with no role takes no new code path. A caller opts in with a header, which is how the MCP server passes a connection's role.
- **Every MCP connection has a role.** The default one withholds val and test data. A user can opt out on the URL.
- **Accidental, not adversarial.** The roles prevent accidental disclosure, accidental overfitting and accidental damage. They are not a defence against a caller that works to get around them.
- **Safe by default, and complete.** A limited role can call a route only when the route was put in that role. Every route says which roles it is in, and a test fails the build for a route that does not.
- **Harness-tuner's method does not change.** This is a move and a port, not a redesign of how it tunes. Where a rule must change, a person signs it off first.
- **No duplicate code, and no poor shape carried over.** One copy of each calculation and each rule.
- **Each phase stands on its own.** A later phase can wait, or not happen, and the earlier ones are still complete and useful.

## Phases

1. **Move.** Harness-tuner's code and tests come into the Kiln repository, with its gateway and its own skills as they are. It behaves as before. Nothing of the two-repository machinery is built.
2. **Kiln APIs.** The APIs that every client gets (below).
3. **Roles.** The map of routes for each role, the rules for withheld data, the default for MCP connections, and the skill text that explains them. Harness-tuner still runs on its gateway, so this phase is tested with MCP clients alone.
4. **Harness-tuner on Kiln's MCP server and skill.** Its role skills move into Kiln's skill and name endpoints. Its agents connect on the URL of their role. Its copies are removed.
5. **Coherence check.** Nothing is built. A check that every needed update was made: no name of a removed thing is left, every pointer resolves, and the docs and tests match.
6. **Proof.** The gateway's fence tests are rewritten as tests of the tuner roles. An audit against harness-tuner's core concepts, and runs on the demo project. When the proof passes, the gateway is deleted.
7. **The launcher package.** The PyPI package `harness-tuner` becomes a thin launcher: it gets Kiln's release, installs it, and starts Kiln's copy of harness-tuner. Last, by hand, the owner makes the old repository private.

Phases 1 to 3 need nothing from phase 4. Until phase 4 lands, harness-tuner keeps working on its gateway. If the proof of phase 6 fails, the gateway stays, and the result is still sound: roles for every other MCP client, and the gateway for the loop.

## Roles

A role says two things about a caller of Kiln's API: which routes it may call, and which eval data it may see. This replaces the four scopes of the canceled spec. The owner chose it because it is safe by default and simpler to keep right: a new route is refused for a limited role until someone puts it in.

- **A map of routes.** Every route is in or out of each role. Each pull request that adds a route must decide, and the build fails for a route that does not say.
- **Withheld data.** A role names the splits whose per-item data is withheld (items, result rows, traces) and the splits whose numbers are withheld. These rules are code in the handlers that return such data. They come from the canceled spec ([scope_decisions.md](../harness_tuner_port/scope_decisions.md)).
- **Where.** A request names its role in one header, and the API enforces it. An MCP connection has one role, named in its URL path; the MCP tool passes it on each call. No token, and no memory on the server.
- **A short, fixed list of roles:**

  | Role | Routes | Withheld |
  |---|---|---|
  | REST with no role | All. As today | Nothing |
  | Chat: every MCP connection, by default | All that MCP allows today | Val and test item data, and test numbers |
  | Open: the user opted out on the URL | The same as chat | Nothing |
  | Tuner roles: a few, by job (build, plan, review, read val) | An allow list for each. No route that deletes, edits the task or changes an eval | Val and test item data. Val and test numbers, except that the val-reading role sees val numbers |

- **A request succeeds in full or fails** with a clear error, as the goal. The hard rule: withheld data is never returned.
- **The MCP server is live.** The new default changes what an MCP client can read. The skill text that explains it, and the routes that give val results as numbers, ship in the same release.

## Kiln APIs

Standard REST routes, reached through `call_kiln_api`. No new MCP tools. They come from the switchover spec, with the decisions of its review ([review_fixes.md](../harness_tuner_switchover/review_fixes.md)).

- **Skill bundles.** Create a skill from the path of a folder, and read its files back. Kiln writes the skill with its own datamodel. Text files only. No rule that a name must be new.
- **Smell check.** One route checks a run config for the five smells that code can detect.
- **Significance floor and detectability.**
- **Scores by split, and a paired comparison of two run configs** that returns no rows. An MCP client needs them to confirm on val by numbers. The owner also wants the compare view of the UI to show val and test results, so a clean route for top-level results of a split serves both.
- **The fix of the exact test** that fails above about 1,030 changed pairs.

Harness-tuner's own code may call these routes or import the same code. Either way there is one copy.

## Harness-tuner on Kiln's MCP server and skill (phase 4)

- **Role skills.** They move to `references/client_guidance/harness_tuner/` in Kiln's skill, and name endpoints, as Kiln's knowledge does. The skill copying code and the skill files of harness-tuner are deleted.
- **Connections.** Each agent session connects to Kiln's MCP server on the URL of its role.
- **Gateway tools that are not one API call.** Examples: the val summary, and traces written as files that an agent can search. Each gets a home in the functional spec. The likely answer is a new API.
- **Rules that no role carries** stay in harness-tuner's code. One example is the model policy, which the code already checks before an eval job.
- **Removed:** the gateway, harness-tuner's copy of the knowledge, its API reference docs, its `call_kiln_api` server, its model catalogue, its skill installer, its smell detectors, and its own copies of the measurement calculations.

## Carried over

- The decisions of the switchover review, in [review_fixes.md](../harness_tuner_switchover/review_fixes.md). Its items about version checks, the contract test and the gateway's mapping table no longer apply.
- The rulings on withheld data, in [scope_decisions.md](../harness_tuner_port/scope_decisions.md). Its raw API default and its four scopes are not taken: roles replace the scopes.

## Not in this spec

- Withholding on the raw API by default.
- A port of harness-tuner's noise check. It stays as it is, behind its option. In one repository it imports Kiln's code where it used a copy.
- A UI for harness-tuner.

## Open

- **How the launcher gets and installs Kiln's release** on each platform (phase 7). For the architecture.
- **The cleanup and robustness project** fixes the prompt generators that can copy a held-out item into a prompt. This spec does not work around them. It warns the owner at the end if the fix is not on main.
