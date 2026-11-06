# Backlog: Cache Eviction and Efficiency

## Open

- Pre-existing (behaves the same before phase 2): with the cache on, a mutable `Eval.load_from_file` of a reference-answer eval that needs the `current_config_id` migration leaves an un-migrated readonly copy of that eval in the cache, so a later readonly load returns `current_config_id=None`. Cause: the migration calls `self.configs(readonly=True)`, which loads the eval's own file readonly; the recursion guard skips the migration for that inner copy, and the inner copy gets cached. Repro: /tmp/claude-0/-home-user-Kiln/01554a27-0103-549e-a80d-175eb2caee46/scratchpad/repro_eval_mig_cache.py
