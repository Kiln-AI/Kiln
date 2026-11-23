# Scope decisions reached before this spec was canceled

These are the owner's rulings from the functional spec discussion. Nothing here was built. They are kept as the starting point for a later project that scopes MCP connections.

## Principle

- The scopes prevent accidental disclosure and accidental overfitting. They are not a defence against a caller that works to get around them.
- The API enforces only what it controls. It does not pretend to control file access.

## The four scopes

- `fence_eval_data`: withholds per-item data of the named splits: the items, their result rows and their traces.
- `fence_eval_results`: withholds the numbers of the named splits.
- `block_eval_changes`: the connection cannot
  1. create, edit or delete an eval, a spec or a judge config, or change an eval's default judge;
  2. create, edit or delete eval inputs;
  3. change a dataset run that is in any eval split: edit, re-tag, rate, repair or delete;
  4. give a run a tag that an eval split uses.
- `readonly`: only GET requests that do not stream. No override per route or per caller.

## Where and how

- The scope is in the MCP URL path, as self-describing settings. No token, and no memory on the server.
- Enforced inside the API. The MCP tool passes the scope on its loopback call.
- No project or task pin. Agents pass both ids on every call anyway.
- No API allow list and no named API filters.
- An item is withheld when it is in a fenced split of any eval. Held-out status comes from eval definitions only, not from tag names.
- A dataset run that is in no split is readable.

## Defaults

| Caller | Item data withheld | Numbers withheld |
|---|---|---|
| Raw API, no override | val and test result rows, their traces, and val and test eval inputs | none |
| MCP default (`/mcp`) | val and test: items, rows and traces | test |
| Harness-tuner | same as the MCP default | val and test |
| Opted out on the URL | none | none |

- Only the one UI page that warns before showing test results sends the raw API override.
- Held-out items stored as dataset runs stay readable on the raw API, because the Dataset page shows them. The MCP default withholds them.
- Harness-tuner's loop code sends the override, because it computes val results in code.

## Withheld data in a response

- A request succeeds in full or fails. Nothing is dropped in silence.
- Run lists fail with a clear error when they would include a withheld item.
- The eval-input list uses its existing filter to ask for a readable split. It fails in full if the result would include a withheld item.
- Result rows: the rule looks only at the requested split. An item that is train in one eval and held out in another is a won't-fix.
- A direct read of a withheld item is a clear error.

## Other rulings

- The skill tells MCP users about the default withholding and why: the rule in `references/knowledge/train_val_test.md`, one pointer line in the root `SKILL.md`, and the reason in the error message.
- Val numbers: the score summary routes get an optional `split`, and a new route gives a paired comparison of two run configs without the rows.
- Not mitigated, by decision: Kiln's own API tool inside a task, a tool server at Kiln's own address, and the job error log.
- Dropped: "only evals this run created can be edited".
- The API fixes found here went to a separate cleanup and robustness project.
