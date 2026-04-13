# Worktree Workflow

We use [Worktrunk](https://worktrunk.dev/) to manage git worktrees for parallel development. Each worktree gets its own Zellij session with dedicated ports, a backend server, a frontend dev server, and a coding agent.

## Setup

Run `.config/utils/setup_env.sh` — it installs project dependencies and optionally sets up workspaces (worktrunk, Zellij, and config).

Or manually:

1. Install worktrunk: `brew install worktrunk && wt config shell install`
2. Install Zellij: `brew install zellij`
3. Install worktree TUI: `uv tool install "git+https://github.com/scosman/worktree_tui"`
4. Configure worktree path (one-time, applies to all repos):

```bash
mkdir -p ~/.config/worktrunk
echo 'worktree-path = ".worktrees/{{ branch | sanitize }}"' > ~/.config/worktrunk/config.toml
```

## Command

Just run `wk` and you can manage workspaces!

## Advanced Commands

### Create a new worktree and launch it

```bash
wt switch --create my-feature -x .config/wt/start.sh
```

This creates a branch, sets up the worktree, installs dependencies (via `post-create` hook), then launches a Zellij session with all dev tools.

To branch from something other than `main`:

```bash
wt switch --create my-feature --base other-branch -x .config/wt/start.sh
```

### Launch an existing worktree

```bash
wt switch my-feature -x .config/wt/start.sh
```

If the worktree already exists, this switches to it and launches Zellij. If the worktree was removed but the branch exists, it re-creates the worktree first.

### Switch to a worktree (cd only, no Zellij)

```bash
wt switch my-feature
```

### List all worktrees

```bash
wt list
```

With CI status and line diffs:

```bash
wt list --full
```

Include branches that don't have worktrees:

```bash
wt list --branches
```

### Interactive picker

```bash
wt switch
```

Running `wt switch` with no arguments opens an interactive picker with live diff/log previews.

### Remove a worktree

From inside the worktree:

```bash
wt remove
```

From anywhere:

```bash
wt remove my-feature
```

Force-remove with unmerged commits:

```bash
wt remove -D my-feature
```

### Merge a feature branch

From inside the feature worktree — squashes, rebases, fast-forward merges to main, and cleans up:

```bash
wt merge
```

Merge to a different target:

```bash
wt merge develop
```

Keep the worktree after merging:

```bash
wt merge --no-remove
```

### Quick navigation

```bash
wt switch -         # Previous worktree (like cd -)
wt switch ^         # Default branch (main)
wt switch pr:123    # GitHub PR #123
```

### View full diff of a branch

All changes since branching (committed + uncommitted):

```bash
wt step diff
```

### Commit with LLM-generated message

```bash
wt step commit
```

### Cleanup merged branches

```bash
wt step prune
```

## Keybinds for Option Left/right to switch tabs

In `~/.config/zellij/config.kdl` add:

```
keybinds clear-defaults=true {
  shared_except "locked" {
      bind "Alt b" { GoToPreviousTab; }
      bind "Alt f" { GoToNextTab; }
  }
}
```

## Architecture

- `.config/wt.toml` — project hooks: dependency install on create, Zellij session cleanup on remove
- `.config/wt/start.sh` — launches a Zellij session with per-branch ports (via `hash_port`)
- `.config/wt/layout.kdl` — Zellij layout: terminal, coding agent, backend server, frontend dev server
- `.config/wt/bin/web` — opens the worktree's web UI in a browser (type `web` in the terminal tab)
- `.config/wt/user_settings.sh` — per-user overrides (gitignored); copy from `user_settings.sh.example`
- `.config/wt/config.toml` — worktrunk user config (worktree path template)
