---
status: complete
---

# Git Auto Sync — Project Overview

I'm thinking about doing a new project, and wanted to spec it with you. Early planning/ideation for now. not our formal specs flow yet. 

Generally idea: read basemodel.py. It's the core to our kiln datamodel. It currently is designed to save files to disk, for use in Git, and git adds version tracking/conflict management. However it was always designed to be pluggable: all load/save logic is in this one class, so we could add an alternative backend.       

Issue: less technical users can't work git. The don't remember to sync, they don't remember to push, they def can't handle merge conflicts.                           

Note: merge conflicts are designed to be super rare: datamodel is almost always append only an immutable. However not guaranteed so we need to handle conflicts.                                                 

Core Idea: a feature that still uses git, but is hidden to the user, and accessible to non-technical users.

# High Level Tecnhnical Idea

All edits happen through our fastAPI API. We add a FastAPI middleware for Git management/sync.

 - start API call (middleware): checks git pull has been run recently and we're relatively up to date (few seconds okay, but don't want to start a read or write if it's a week stale). Trigger sync/pull if out of date (blocking API call start until we're up to sync, and failing if sync fails). All APIs share a git manager singleton for this, so we're not making many parallel syncs. 
 - API call: API code runs normally. Under the hood the datamodel is running normally, writing files locally.
 - end API call (middleware): we "commit" all changed made in this API call as a batch. See "hard part" below.
 - background process: keep git sync/pull up to date every few seconds from python process. Poll I think unless there's a notification channel? Goal is that start API call never hangs waiting for sync, execept maybe on startup.

# UX

### Auto vs Manual

User can be in "auto" mode or "manual mode". Existing mode is manual. Auto mode manages git pull/sync/merge for you. Should be able to toggle on/off.

### Login

Eventually we'll have a nice login UX for github: oAuth link, list projects, etc.

For V1 can use your default creds.

Later: 
 - will need non-github option too.
 - will need to support creds per project (one project on gitlab, another on github)

### Code

Code should live in `/app` as this will be paid feature.

# Hard Questions

### Git mode: Rebase Only

I think projet should be rebase only?

### Safe Commit

Committing safely, robustly, and with zero-management isn't easy.

Concerns:

 - 1 API may edit many many files, not just 1. The commit should be atomic per API endpoint, never committing/syncing partial state part way through API call, which might be invalid.
 - merge conflict: server could change between read and write and then our local writes have a conflict. While this will be rare (few second sync gap, generally append only system) we need to handle it.
 - parallelism: making 2 API calls at a time can edit different sets
 - rollback on push failure: we want "online" experience. If they are offline and can't push, they risk getting more and more out of sync, accumulating iresolvable git conflicts. We want the API call to fail, and to rollback disk changes, if push doesn't work on the middleware wrap up.
 - push robustness: we don't want push to overwite changes from others (many people pushing in parallel). But we don't want a global lock either (only 1 api call at a time, across all users). Want a "fail and rollback" someone else touched the same files, but otherwise work.
 - non-API changes: we can enfoce all API calls 
 - APIs scoped to projects: do we always have project_id in API calls that write? we should because that's needed to get any data model, but enforcing this might be interesting.

#### Parallelism Details

If the client makes 2 API calls in parallel it'll be hard to manage the commit on per-api call basis. One could succeed and UI shows success, one could fail. Some of the files of one could get pulled into other commit but second commit fails, leaving partial/broken state.

# Tech Notes:

 - want it to be embedded in app, not shelling out to CLI (user not technical). AKA: libgit2/pygit2, not GitPython.
 - we want a general purpose library for "auto-batch-sync" or similar, implemented and tested on it's own, with a nice clean integration into the app. Essentially just in the middleware lives in project (and later setup UX).
 
# Specing note

There are a lot of unknowns. We should wrap up the "Hard part" plan in feature planning. Expect more iteration than typical, ask more questions, propose more options/tradeoffs. This is more interactive design.