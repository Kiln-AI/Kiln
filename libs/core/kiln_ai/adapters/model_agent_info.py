"""The vocabulary for agent-facing notes and tags in the model list and provider list.

`KilnModel.agent_notes`, `KilnModel.tags`, `KilnModelProvider.tags`, and the
`notes` and `tags` of each `KilnProviderInfo` are written for agents that choose
or configure a model. The rules here are enforced by tests on the built-in data,
never at parse time, so an older client keeps loading a newer remote config.

Each tag's meaning is a claim compared with models at the same price. A new tag
goes into the right map, with its meaning, in the same change that first uses it.
"""

import re
from typing import Final, Mapping

TAG_PATTERN: Final = re.compile(r"^[a-z0-9_]{1,40}$")
MAX_TAGS_PER_ENTRY: Final = 12
MAX_NOTE_CHARS: Final = 2000

# Tags for KilnModel.tags: true of the model on every provider.
MODEL_TAGS: Final[Mapping[str, str]] = {
    "best_value": "Its quality for its price is among the best at that price.",
    "strong_agentic": "Reliable in multi-step tool use and agent loops, compared with models at the same price.",
    "strong_coding": "Strong at writing and fixing code, compared with models at the same price.",
    "strong_writing": "Strong at prose: tone, style and following a writing brief, compared with models at the same price.",
    "verbose": "Its answers are usually longer than asked, or longer than those of similar models.",
}

# Tags for KilnModelProvider.tags: true of one provider entry of a model only.
PROVIDER_ENTRY_TAGS: Final[Mapping[str, str]] = {
    "very_fast": "Output speed is much higher than usual for a model of this size, usually on special hardware.",
    "fast": "Output speed is higher than usual for a model of this size and price.",
}

# Tags for KilnProviderInfo.tags: true of the provider as a whole.
PROVIDER_LIST_TAGS: Final[Mapping[str, str]] = {}
