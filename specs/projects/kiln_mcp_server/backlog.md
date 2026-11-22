# Backlog

- [ ] **B1 — The PyInstaller hook bundles dotfiles that the skill index skips**
  `app/desktop/pyinstaller_hooks/hook-kiln_mcp_server.py` uses `collect_data_files("kiln_mcp_server")`, which bundles dotfiles (for example a Finder `.DS_Store` in `skill/`), while `build_index` skips them. So `test_the_bundled_data_is_exactly_the_skill_tree` would fail on a Mac checkout with a stray dotfile. Consider `excludes=["**/.*"]` (verify the glob behaviour on hidden folders) plus a test.
