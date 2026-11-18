"""The vocabulary for agent-facing notes and tags in the model list and provider list.

`KilnModel.agent_notes`, `KilnModel.tags`, `KilnModelProvider.tags`, and the
`notes` and `tags` of each `KilnProviderInfo` are written for agents that choose
or configure a model, such as the Harness Tuner optimizer or the Kiln assistant.
The rules here are enforced by tests on the built-in data, never at parse time,
so an older client keeps loading a newer remote config.

Every tag except ``current`` is a set tag. The ``current`` procedure and the
set-review procedure are in ``claude-maintain-models``. See the tag maps below
for each tag's meaning, kind and limit.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping

TAG_PATTERN: Final = re.compile(r"^[a-z0-9_]{1,40}$")
MAX_TAGS_PER_ENTRY: Final = 12
MAX_NOTE_CHARS: Final = 2000


class TagKind(str, Enum):
    lineage = "lineage"
    set = "set"


@dataclass(frozen=True)
class TagInfo:
    meaning: str
    kind: TagKind
    max_models: int | None  # set tags only; None for lineage


# Tags for KilnModel.tags: true of the model on every provider.
MODEL_TAGS: Final[Mapping[str, TagInfo]] = {
    "current": TagInfo(
        "The lab's best offering at this price level. A model without this"
        " tag is superseded: do not choose it for a new run config unless"
        " asked.",
        TagKind.lineage,
        None,
    ),
    "recommended": TagInfo(
        "A model we recommend as a candidate for new agents. Always also `current`.",
        TagKind.set,
        20,
    ),
    "top_value": TagInfo(
        "Among the best quality for its cost, at a low or mid price."
        " A top-price model is never in this set, however good its value."
        " Look at these first when optimizing for cost.",
        TagKind.set,
        14,
    ),
    "top_fast": TagInfo(
        "Among the fastest models for latency-sensitive work, by output"
        " speed and time to first token, or a faster hosted version of a"
        " strong model.",
        TagKind.set,
        14,
    ),
    "top_on_device": TagInfo(
        "Among the best models that run on consumer laptops or phones.",
        TagKind.set,
        14,
    ),
    "top_open": TagInfo(
        "Among the best open-weight models, across a range of sizes.",
        TagKind.set,
        14,
    ),
    "top_writing": TagInfo(
        "Among the best at prose: tone, style and following a writing brief.",
        TagKind.set,
        14,
    ),
}

# Tags for KilnModelProvider.tags: true of one provider entry only.
# Empty; kept for later use.
PROVIDER_ENTRY_TAGS: Final[Mapping[str, TagInfo]] = {}

# Tags for KilnProviderInfo.tags: true of the provider as a whole.
# Empty; kept for later use.
PROVIDER_LIST_TAGS: Final[Mapping[str, TagInfo]] = {}

# Words that must not appear in a model note, as whole words, case-insensitive.
# A note must not need edits as it ages. The ``current`` tag and the
# ``Superseded by:`` line are the only places that show age.
BANNED_NOTE_WORDS: Final = (
    "current",
    "latest",
    "newest",
    "now",
    "previous",
    "frontier",
    "state of the art",
    "best",
    "peers",
)

# Labels of a model note, in the required order.
MODEL_NOTE_LABELS: Final = (
    "Description:",
    "Lineup:",
    "Superseded by:",
    "Same weights:",
    "Useful for:",
    "Strengths:",
    "Behavior:",
    "Deployment:",
)

# Labels of a provider note, in the required order.
PROVIDER_NOTE_LABELS: Final = (
    "Data retention:",
    "Rate limits:",
    "Routing:",
    "Gotchas:",
)
