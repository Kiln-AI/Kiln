---
status: complete
---

# Git Sync Write Locks


### Context: 

That spec describes a process “Long-Running Write Requests” where some requests can manage their own write lock. We haven’t updated the needed endpoints to use this. This project is to ensure everything that needs a write lock is using a write lock.

### Discover all places that need updates

Any file-writes should happen inside a write lock. Most get this for free (POST/PATCH API requests). But we need to find cases where it’s missing.

- SSE endpoints: need to be GET even though they may make writes. Most likely need write locks added. We should audit all. Example: `GET /api/projects/461025716436/rag_configs/300362130551/run` makes a dirty write, and the change is blow away.
- any file writes/deletes/mode in the project that aren’t part of an API endpoint? Background jobs? Startup?

### Improve Detection of Issues

The git_auto_sync spec defined dev-mode safety nets. They aren’t working well. The log is minimal (`Repo dirty on write request -- running crash recovery`), it doesn’t attribute which API call left it dirty, and doesn’t appear until later

- make it do a dirty check after each API and write a much better warning/log, attributing it to which API was the cause.
- can we make the API error (500) so we catch this? Or append a warning to output (which will break json parsing, so we catch it). Dev mode only

