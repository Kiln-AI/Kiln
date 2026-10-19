---
status: complete
---

# Phase 1: `RUF059` sweep

## Overview

Clear all 74 `RUF059` unused-unpacked-variable findings under `app/desktop/`, so that when
Phase 4 flips the ruff config the rule is already clean. No behaviour changes: every fix is
an underscore-prefix rename of a binding that was never read, the deletion of a statement whose
every binding was unread, or — in the two cases where a sibling test proves the assertion was
dropped — the assertion the test meant to make.

Ruff's own fix for `RUF059` is classified unsafe (renaming a binding can collide), so nothing
here is applied with `--fix`. Every site is read and edited.

## Site survey

66 source lines carry the 74 findings (eight lines have two unused slots each).

| Shape | Sites | Verdict |
|---|---|---|
| `local_path, remote_path = git_repos` and friends, one slot read | 49 lines | Fixture tuple unpack of filesystem paths. Nothing is under test here, so nothing can be a missing assertion. Underscore-prefix the unread slot. |
| The same unpack with *no* slot read | 13 lines | The whole statement is dead — see below. Delete it. |
| `success, msg, mode = check_remote_access(...)` | `test_clone.py` 319, 346 | Read individually — see below. |
| `branches, default = list_remote_branches(...)` | `test_clone.py` 395, 407 | Both tests are named for the default-branch fallback and assert `default`. The branch list has its own test (`test_ignores_tags`) in the same class. Underscore-prefix. |
| `success, msg, denied = check_write_access(...)` | `test_clone.py` 486, 502, 518, 623, 656, 676, 692, 709, 730 | Each asserts the outcome it is named for (repo freed / denied classification / commit rolled back). 623 is a recovered assertion — see below. Underscore-prefix the rest. |
| `mock_client, get_call_count = make_n_round_mock_client(...)` | `chat/test_routes.py` 815 | The test asserts the continuation round through `mock_client.stream.call_args`; the round counter is redundant, and the sibling test 40 lines below already discards it. Underscore-prefix. |

### Missing assertion 1 of 2

`test_clone.py:319`, `TestTestRemoteAccess.test_success_with_pat`:

```python
success, msg, mode = check_remote_access(
    "https://github.com/org/repo.git", pat_token="ghp_token"
)
assert success is True
assert mode == "pat_token"
```

Its sibling `test_success_system_keys` — same function, same success path — asserts all three
slots including `assert msg == "Access successful"`. `test_remote_access` in
`git_sync/clone.py:176` returns that exact literal on every success path regardless of mode, so
the assertion is provably correct rather than speculative. Add it.

`test_clone.py:346` (`test_explicit_auth_mode`) is deliberately *not* given the same treatment.
That test exists to prove `auth_mode` is forwarded to `_ls_remote_pygit2` — it ends in an
`assert_called_once_with` — and asserting the success message there would be padding, not a
recovered assertion.

### Missing assertion 2 of 2

`test_clone.py:623`, `TestWriteAccessDeniedClassification.test_generic_git_error_does_not_set_write_denied`,
is the only test in its class that does not assert message content — its three siblings assert
`"permission denied"`, `"read-only"`, and `"authentication failed"` respectively.

The class exists to pin which of `check_write_access`'s four failure returns was taken, and the
message is half of what distinguishes them. This test drives the generic fall-through with
`GitError("network timeout")`, and `clone.py:481` returns `f"Write access check failed: {e}"`
there, so `assert "network timeout" in msg` is provably correct. It is also the assertion that
does the most work in this class: `"network timeout"` matches none of the `403`/`401`/`auth`
substrings the earlier branches test for, so it pins that control flow reached the fall-through
rather than an earlier `return` that happens to also set `denied` to `False`. Add it.

### The thirteen dead statements

Thirteen sites unpack `git_repos` without reading any slot — the entire statement is dead. Four
name both slots (`local_path, remote_path = git_repos`, both unread) and nine already discard
one (`local_path, _ = git_repos` or `_, remote_path = git_repos`, with the named slot unread
too). Underscore-prefixing them (`_local_path, _remote_path = git_repos`) would satisfy the
linter while leaving dead code behind, so the statement is deleted instead. This is provably
behaviour-preserving: each test still requests `git_repos` in its signature, so the fixture
still builds both repos, and `git_repos` (`app/desktop/git_sync/conftest.py:35`) does all its
work in the fixture body and returns a plain `(local_path, remote_path)` tuple — unpacking it
has no side effects. These tests drive the repo through `api_ctx` / `write_ctx` / `manager`
rather than through the paths.

Sites: `test_conflicts.py` 146, 332; `test_crash_recovery.py` 337; `test_freshness.py` 27, 117,
146; `test_locking.py` 193; `test_network_failure.py` 40, 227, 255; `test_rollback.py` 72, 152;
`test_git_sync_manager.py` 347.

## Steps

1. Apply the underscore-prefix rename at every `RUF059` site, driven off ruff's own
   `file:line:col` output so each edit lands on the exact reported token:
   `local_path, remote_path = git_repos` becomes `local_path, _remote_path = git_repos`,
   `success, msg, mode = ...` becomes `success, _msg, mode = ...`, and so on.
2. Revert the rename at the two recovered-assertion sites and add the assertion each test meant
   to make.
3. Delete the thirteen dead unpack statements, then run `uv run ruff format` on the affected
   files — removing a statement can leave a docstring adjacent to a nested `def`.
4. Read the full diff — it must contain only leading underscores, the thirteen deletions, and
   the two added assertions.
5. Confirm no renamed binding shadows or collides with an existing name in its scope (ruff's
   `F811`/`F841` and the test run cover this).
6. Grep for any statement whose bindings are *all* discarded, to prove none of the renames left
   dead code behind:
   `grep -rnE '^\s*(_\w*|_)\s*,\s*(_\w*|_)\s*(,\s*(_\w*|_)\s*)*=' app/desktop --include=*.py`

## Tests

No new tests. This phase adds no behaviour; the existing desktop suite is the safety net, and
it is the right one — all 74 sites are in test files, so a rename that broke a reference fails
loudly.

- `uv run ruff check --config pyproject.toml --exclude app/desktop/studio_server/api_client/kiln_ai_server_client --select RUF059 app/desktop` reports zero findings.
- The same command with no `--select` reports 73 findings (147 minus this phase's 74), proving
  nothing else regressed.
- `uv run python3 -m pytest --benchmark-quiet -q -n auto app/desktop` passes, including both
  tests carrying a new assertion. Each new assertion is mutation-checked: altering the expected
  substring must fail the test, proving it is not vacuous.
- `uv run ruff format --check .` passes.
