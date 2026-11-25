# Backlog: Cache Eviction and Efficiency

## Open

None.

## Closed

- Pre-existing (behaves the same before phase 2): with the cache on, a mutable `Eval.load_from_file` of a reference-answer eval that needs the `current_config_id` migration leaves an un-migrated readonly copy of that eval in the cache, so a later readonly load returns `current_config_id=None`. Cause: the migration calls `self.configs(readonly=True)`, which loads the eval's own file readonly; the recursion guard skips the migration for that inner copy, and the inner copy gets cached. Repro: /tmp/claude-0/-home-user-Kiln/01554a27-0103-549e-a80d-175eb2caee46/scratchpad/repro_eval_mig_cache.py
  - **Closed in phase 8.** The migration finds the config files without loading their parent (`KilnParentedModel.iterate_children_paths_in_folder`) and loads each config with the eval as its parent, so it never reads the eval's own file. That also fixes the readonly configs cached in that pass holding the un-migrated copy as their parent. The recursion guard is gone.
- Phase 4 code (lazy_fields.py `_restore`): only FileNotFoundError, OSError, JSONDecodeError and ValueError are wrapped. An AttributeError raised during re-validation would make `getattr(run, "trace", None)` return None and `hasattr` return False — the silent fallback functional spec §3 guarantee 5 forbids. TypeError/KeyError also surface without the file name. Latent: no `getattr`-with-default or `hasattr` on a large field exists in libs/ or app/desktop today. Fix: wrap any other exception from `root.revalidate` in `LargeFieldUnavailableError`.
  - **Closed in phase 8.** `_restore` wraps any other exception in `LargeFieldUnavailableError`, naming the file, the field and the exception type.
- Pre-existing, flagged in phase 6: the JSONL export (`dataset_formatter.py`) stays mutable as the spec decided, but it loads every run of the task as an editable copy, not only the split's runs. So each export reads back (and deep-copies) the large fields of the whole task — on a 25k-run task, a large memory and disk-read spike. Possible fix: load the task's runs readonly, filter to the split's ids, and take editable copies (or plain reads) of only those runs.
  - **Closed in phase 8.** Nothing in the export path edits, saves or hands a run to code that does, so the export loads the task's runs readonly. Only the split's runs read their large fields.

## Dismissed

- Spec problem, decision needed: the cache budget uses the host's physical RAM (`os.sysconf("SC_PHYS_PAGES")` in `physical_memory_bytes`), which ignores Linux cgroup/container memory limits. Example: `kiln_server` in a container with a 1 GiB limit on a 32 GiB host gets a 2 GiB budget and can be OOM-killed. New risk, because the cache never ran on Linux before this project. Possible fix: on Linux also read `/sys/fs/cgroup/memory.max` (cgroup v2) and take the smaller value.
  - **Dismissed in phase 8:** the user decided won't fix.
- Phase 4 code (lazy_fields.py `_restore`, with utils/torn_read.py `retry_on_torn_read`): a restore that meets a save in progress fails and isn't retried. `save_to_file` truncates and rewrites in place; `_restore` turns the resulting `json.JSONDecodeError` into `LargeFieldUnavailableError`, which `retry_on_torn_read` doesn't catch. New transient failure (eval item error or API 500), rare, no data loss. Fix options: retry once inside `_restore` on `JSONDecodeError`, or have `retry_on_torn_read` treat a `LargeFieldUnavailableError` caused by `JSONDecodeError` as a torn read.
  - **Dismissed in phase 8:** the user decided to leave it as is. No data is lost, and the next load caches the record.
