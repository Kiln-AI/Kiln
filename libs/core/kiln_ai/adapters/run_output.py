from dataclasses import dataclass
from typing import Dict


@dataclass
class RunOutput:
    output: Dict | str
    intermediate_outputs: Dict[str, str] | None
