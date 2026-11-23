# PyInstaller does not bundle package data by itself. Every non-Python file of
# kiln_mcp_server is its skill tree, which the MCP server reads at run time.
from PyInstaller.utils.hooks import collect_data_files

# The skill index skips hidden names, so the bundle does too: a stray
# `.DS_Store` would otherwise ship. The glob also matches hidden folders.
DATA_EXCLUDES = ["**/.*"]

datas = collect_data_files("kiln_mcp_server", excludes=DATA_EXCLUDES)
