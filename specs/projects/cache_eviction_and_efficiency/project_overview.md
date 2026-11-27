---
status: complete
---

# Cache Eviction and Efficiency

## Background

Kiln is built on a datamodel where our "database" is JSON files on disk, synced through git. This is an intentional design.

The datamodel layer has a cache: first load may be a bit slow (need to validate/parse) but after that, it's served from memory cache. File-watching ensures we refresh memory cache when needed, per object (a fast FS call that it hasn't changed on linux, and I think a watcher with cache eviction too — it's been a while).

The nice part: to devs it just feels like pydantic data models. But perf is somewhat free.

This worked well for a long time. But now sometimes we have 25,000 multi-turn task runs. This eats memory fast.

I want to explore a series of perf fixes.

## Cache eviction

- Cache eviction is key: some large data models are read once and never used again. We should be able to evict on occasion.
  - When to evict: memory pressure, idle time, maybe others.
  - Priority: LRU? LRU+size balanced? Open to suggestions.
- Ideally same API: no change for data-model subclasses. No change for consumers.

## Large fields

- Some of our datamodel fields can be huge: a 100 turn trace with reasoning. This is more true now than before, when we had only single turn. But some others are also large (RAG docs).
- Generally these "huge" fields are needed less often than the top level metadata (created_at, name), which are needed for list operations.
- Yet the cache treats them the same.
- Simple example: a task with 100k runs loads 100k traces into memory to load the /dataset page. We just need name and timestamp for the top level page.
- Basically we want to keep: in memory and fast for 99% of accesses (list operations), and do full reads for the occasional API call that needs it.
- Can we label some fields and give them custom cache treatment? A decorator that impacts caching.
  - Default
  - No cache: don't cache at all. Forces a disk call each read.
  - Low priority: cache, but evicted sooner than we would the whole object.
  - High priority: we know this is needed often (dataset items name/created_at) so don't evict unless we really have to.
- Can we make them lazy-load in a way that consumers don't need to change?
  - The dataset item details page still needs the full trace.
- How much code change is needed to prevent large fields filling the cache?
  - Does the list API used by the dataset page need a version that doesn't just json_dump, and instead only returns set fields? How many APIs would need to be changed?
  - Any functionality changes needed?
- Which fields should we target?

## Library mode

We have an app mode and a library mode. We should ensure the cache is off by default in library mode (and on for app mode and service mode).
