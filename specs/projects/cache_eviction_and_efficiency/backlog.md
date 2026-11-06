# Backlog: Cache Eviction and Efficiency

## Open

- Pre-existing (behaves the same before phase 2): with the cache on, a mutable `Eval.load_from_file` of a reference-answer eval that needs the `current_config_id` migration leaves an un-migrated readonly copy of that eval in the cache, so a later readonly load returns `current_config_id=None`. Cause: the migration calls `self.configs(readonly=True)`, which loads the eval's own file readonly; the recursion guard skips the migration for that inner copy, and the inner copy gets cached. Repro: /tmp/claude-0/-home-user-Kiln/01554a27-0103-549e-a80d-175eb2caee46/scratchpad/repro_eval_mig_cache.py
- Spec problem, decision needed: the cache budget uses the host's physical RAM (`os.sysconf("SC_PHYS_PAGES")` in `physical_memory_bytes`), which ignores Linux cgroup/container memory limits. Example: `kiln_server` in a container with a 1 GiB limit on a 32 GiB host gets a 2 GiB budget and can be OOM-killed. New risk, because the cache never ran on Linux before this project. Possible fix: on Linux also read `/sys/fs/cgroup/memory.max` (cgroup v2) and take the smaller value.
