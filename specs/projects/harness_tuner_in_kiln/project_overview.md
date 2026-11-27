---
status: complete
---

# Harness Tuner in Kiln

Move harness-tuner into the Kiln repository, give MCP connections scopes, and put harness-tuner's agents on Kiln's own MCP server and skill.

This spec replaces [harness_tuner_switchover](../harness_tuner_switchover/project_overview.md), which kept harness-tuner in its own repository with its own gateway. It takes up the scopes plan of [harness_tuner_port](../harness_tuner_port/project_overview.md), which was canceled. The MCP server itself, [kiln_mcp_server](../kiln_mcp_server/project_overview.md), is merged to main and live.

## Why

- **Two repositories.** Harness-tuner holds copies of things Kiln owns, and the two need machinery to stay in step: version checks both ways, a contract test, and a reader of Kiln's skill over MCP.
- **Two tool surfaces.** Harness-tuner's agents use its gateway, with tools of its own. Kiln's knowledge names Kiln's endpoints. So every endpoint needs a second name and a table between the two.
- **No protection for other MCP clients.** A chat client on Kiln's MCP server can read val and test data today. Only the skill's text tells it not to.
- **A second install.** A Kiln user must install a separate project to use harness-tuner.

## The end state

- **One repository and one release.** Harness-tuner ships with the Kiln app.
- **One skill.** Harness-tuner's role procedures are in Kiln's skill, beside the knowledge they use.
- **One API and one MCP server.** Harness-tuner's agents get the same two tools as every MCP client: `call_kiln_api` and `kiln_skill`.
- **One fence.** A scope on the MCP connection, enforced in Kiln's API. Every MCP client gets it.

Harness-tuner's own Python code is trusted. It calls Kiln with no scope and keeps val and test data away from its agents itself, as it does today. The scopes are for agents.

## Principles

- **The REST API does not change by default.** A request with no scope takes no new code path. A caller opts in with a header, which is how the MCP server passes a connection's scope.
- **Every MCP connection has a scope by default.** A user can opt out on the URL.
- **Accidental, not adversarial.** The scopes prevent accidental disclosure and accidental overfitting. They are not a defence against a caller that works to get around them.
- **Complete.** Every route is classified for the scopes, and a test fails the build for a route that is not.
- **Harness-tuner's method does not change.** This is a move and a port, not a redesign of how it tunes.
- **No duplicate code, and no poor shape carried over.** One copy of each calculation and each rule.
- **Each phase stands on its own.** A later phase can wait, or not happen, and the earlier ones are still complete and useful.

## Phases

1. **Move.** Harness-tuner's code and tests come into the Kiln repository, with its gateway and its own skills as they are. It behaves as before. Nothing of the two-repository machinery is built.
2. **Kiln APIs.** The APIs that every client gets (below).
3. **Scopes.** The four scopes, the default for MCP connections, and the skill text that explains them. Harness-tuner still runs on its gateway, so this phase is tested with MCP clients alone.
4. **Harness-tuner on Kiln's MCP server and skill.** Its role skills move into Kiln's skill and name endpoints. Its agents connect on scoped URLs. Its copies are removed.
5. **Proof.** The gateway's fence tests are rewritten as scope tests. An audit against harness-tuner's core concepts, and runs on the demo project. When the proof passes, the gateway is deleted.

Phases 1 to 3 need nothing from phase 4. Until phase 4 lands, harness-tuner keeps working on its gateway. If the proof of phase 5 fails, the gateway stays, and the result is still sound: scopes for every other MCP client, and the gateway for the loop.

## Scopes

The design is the one reached in the canceled spec ([scope_decisions.md](../harness_tuner_port/scope_decisions.md)), with one change: the raw API withholds nothing by default.

- **Four scopes:**
  - `fence_eval_data`: withholds the per-item data of the named splits: the items, their result rows and their traces.
  - `fence_eval_results`: withholds the numbers of the named splits.
  - `block_eval_changes`: no changes to evals, judges or eval inputs, and no changes to dataset items that are in an eval split.
  - `readonly`: only GET requests that do not stream.
- **Where.** The scope is in the MCP URL path, as self-describing settings. No token, and no memory on the server. The MCP tool passes the scope to the API on its loopback call, and the API enforces it.
- **No tool lists.** Every connection has the same two tools and the same API. The scopes are the only limit. There is no list of allowed tools or routes for a role.
- **Defaults:**

  | Connection | Withheld |
  |---|---|
  | REST with no scope | Nothing. As today |
  | Every MCP connection, by default | Val and test item data, and test numbers |
  | Harness-tuner's train-side roles | The same, and val numbers. `block_eval_changes` is on |
  | Harness-tuner's two val-reading roles | They see val numbers, and are `readonly` |
  | Opted out on the URL | Nothing |

- **A request succeeds in full or fails** with a clear error. Nothing is dropped in silence.
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
- **Connections.** Each agent session connects to Kiln's MCP server on a scoped URL for its role.
- **Gateway tools that are not one API call.** Examples: the val summary, and traces written as files that an agent can search. Each gets a home in the functional spec. The likely answer is a new API.
- **Rules that are not scopes** stay in harness-tuner's code. One example is the model policy, which the code already checks before an eval job.
- **Removed:** the gateway, harness-tuner's copy of the knowledge, its API reference docs, its `call_kiln_api` server, its model catalogue, its skill installer, its smell detectors, and its own copies of the measurement calculations.

## Carried over

- The decisions of the switchover review, in [review_fixes.md](../harness_tuner_switchover/review_fixes.md). Its items about version checks, the contract test and the gateway's mapping table no longer apply.
- The scope rulings, in [scope_decisions.md](../harness_tuner_port/scope_decisions.md), except its raw API default.

## Not in this spec

- Withholding on the raw API by default.
- A port of harness-tuner's noise check. It stays as it is, behind its option. In one repository it imports Kiln's code where it used a copy.
- A UI for harness-tuner.

## Open

- **Packaging.** How the command line, PyPI and the app bundle fit together. It does not block the plan.
- **Harness-tuner's own code: REST or import.** This follows from the packaging.
- **The cleanup and robustness project.** The canceled spec relied on its fixes, such as the prompt generators that skip items of an eval split. To check: which of them this spec needs before the scopes are complete.
- **Three places where the gateway is stricter than the scopes.** It returns only named fields. It treats a tag named like `holdout` as held out when no eval uses it. It takes out an item that is train in one eval and held out in another. The functional spec says for each whether the scopes match it or the gap is accepted.
