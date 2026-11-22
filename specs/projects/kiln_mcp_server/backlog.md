# Backlog

- [ ] **B1 — The PyInstaller hook bundles dotfiles that the skill index skips**
  `app/desktop/pyinstaller_hooks/hook-kiln_mcp_server.py` uses `collect_data_files("kiln_mcp_server")`, which bundles dotfiles (for example a Finder `.DS_Store` in `skill/`), while `build_index` skips them. So `test_the_bundled_data_is_exactly_the_skill_tree` would fail on a Mac checkout with a stray dotfile. Consider `excludes=["**/.*"]` (verify the glob behaviour on hidden folders) plus a test.
- [ ] **B2 — Error texts 7 and 8 append a sentence to a core text with no closing full stop**
  In `app/mcp/kiln_mcp_server/api_tool/messages.py`, `request_failed` (text 7: timeout or connection failure) and `response_unusable` (text 8: response not JSON, or jq failed) append a sentence to the core `KilnApiCallTool` text, which has no closing full stop. Agents see, for example, "Request to /api/items/1 timed out after 30.0s The PATCH may have taken effect." Joining with ". " when the core text lacks end punctuation changes text the spec fixes, so it needs the owner's decision. Also relevant to the text tuning of phase 10.
- [ ] **B3 — The wrong-method text lists MCP-blocked methods**
  `RouteIndex.match` and `messages.wrong_method` list every method of a path, including MCP-blocked ones. Once the block list lands, `DELETE /api/settings` answers "This path supports: GET, POST" while `POST /api/settings` is blocked, which invites a call that is then refused. Design decision: filter blocked methods from the list, or keep the spec's "the path's methods".
