# Git Auto Sync

Automatic, transparent git-based synchronization for Kiln projects. Users get cloud sync, version history, and multi-user collaboration without needing to know what git is. The system handles pull, commit, push, conflict resolution, and crash recovery automatically.

## Design Goals

- **User-friendly**: Non-technical users can connect, clone, commit, and pull entirely through the Kiln UI -- no git knowledge required. Setup uses a personal access token (with a deep link to GitHub's token creation page).
- **Multi-user**: Designed for many parallel users. The Kiln data model uses small, frequent commits, and most objects are immutable/append-only, making conflicts extremely rare.
- **Online-only**: To prevent conflicts, the local repo stays within 15 seconds of the remote via background polling. Going offline will block reads and writes (503 errors) rather than silently diverge.

Note: A developer or someone familiar with git is needed to create the repository initially. After that, non-technical users can do everything from the Kiln UI.

## Key Assumptions

**Kiln owns the repo.** Auto-sync always clones into a hidden, Kiln-managed directory (`.git-projects/` inside the Kiln projects folder). It never uses an existing checkout. This guarantees:

- No interference from editors, IDEs, or other tools
- `git status` is a reliable single source of truth for what changed
- Clean, predictable repo state for the sync system

If you want to make local changes to the repo, use a separate clone -- don't modify files in the hidden Kiln-managed directory.

## How It Works

Git sync operates at the **HTTP middleware layer**. No changes to `KilnBaseModel` or `libs/core/` are needed -- file I/O happens exactly as it does today, and the sync system observes changes via `git status` after the fact.

- **Online**: A background poller keeps the local repo within seconds of the remote. It pauses after 5 minutes of inactivity and resumes on the next API request.
- **Fast, small commits**: Every API call that mutates your project immediately commits and pushes the changes.
- **Conflict avoidance**: Conflicts are exceedingly rare -- the combination of staying within 15 seconds of remote and the Kiln data model being primarily append-only (with unique ID-based file paths) means two users almost never touch the same file.
- **Conflict resolution**: Conflicts are detected during API calls and resolved immediately. The API call fails, changes are rolled back atomically, and the repo is brought up to date with the remote. Retrying the API call will now succeed since the client is up to date.
- **No data loss**: Changes are always committed, or in rare conflict cases, stashed. No data is ever deleted.

For the full technical details (request lifecycle, locking, rebase strategy, crash recovery), see the [functional spec](../../../specs/projects/git_auto_sync/functional_spec.md) and [architecture](../../../specs/projects/git_auto_sync/architecture.md).

