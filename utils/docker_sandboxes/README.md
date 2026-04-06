# Using Docker Sandboxes

## Enable docker sandboxes in `wk`

make a copy of `cp .config/wk/user_settings.sh.example .config/wk/user_settings.sh` and uncomment the docker block.

## Create Your Sandbox

Manual run (good to run to check it works, but will be run for you if using `wk`):
```bash
./utils/docker_sandboxes/create_sandbox.sh
```

Note: log into claude code on your first run


## Deps

All worktrees share a sandbox, but that also means they share deps. 

Separate sandboxes work, but require you to login every single worktree which is painful.

## Fresh build

Run on occasion to make your sandbox template more up to date. Forking a worktree will be faster.

```bash
./utils/docker_sandboxes/create_sandbox.sh --rebuild-all
```

To use bash:
```bash
docker sandbox exec -it claude-kiln bash
```

## Pending / Improvements

- Docker can't handle parallel tests. Might need more memory? Detects and runs single threaded now
- Independent sandbox per worktree with .venv and node_modules in worktrees. Easy to get (just edit sandbox_name.sh) but haven't solved how to auto-log in.
