from typing import Any

"""
The PyPI jq wheel is only a native extension. There is no 
importable .py package layout, and ty does not treat that 
.so as the jq module, so you get unresolved-import even though 
uv run python -c "import jq" works

This file is a stub to satisfy ty's type checker.
"""

def compile(program: str) -> _Program: ...

class _Program:
    def input_value(self, value: Any) -> _ProgramWithInput: ...

class _ProgramWithInput:
    def text(self) -> str: ...
