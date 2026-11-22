# PyInstaller does not bundle package data by itself. Every non-Python file of
# kiln_mcp_server is its skill tree, which the MCP server reads at run time.
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("kiln_mcp_server")
