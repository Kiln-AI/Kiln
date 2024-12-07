from random import choice
from typing import List

ADJECTIVES: List[str] = [
    "Curious",
    "Playful",
    "Mighty",
    "Gentle",
    "Clever",
    "Brave",
    "Cosmic",
    "Dancing",
    "Electric",
    "Fierce",
    "Glowing",
    "Hidden",
    "Infinite",
    "Jolly",
    "Magical",
    "Ancient",
    "Blazing",
    "Celestial",
    "Dazzling",
    "Emerald",
    "Floating",
    "Graceful",
    "Harmonious",
    "Icy",
    "Jade",
    "Kinetic",
    "Luminous",
    "Mystic",
    "Noble",
    "Opal",
    "Peaceful",
    "Quantum",
    "Radiant",
    "Silent",
    "Thundering",
    "Untamed",
    "Vibrant",
    "Whispering",
    "Xenial",
    "Yearning",
    "Zealous",
    "Astral",
    "Boundless",
    "Crimson",
    "Divine",
    "Ethereal",
    "Fabled",
    "Golden",
    "Heroic",
    "Imperial",
]

NOUNS: List[str] = [
    "Penguin",
    "Dragon",
    "Phoenix",
    "Tiger",
    "Dolphin",
    "Mountain",
    "River",
    "Forest",
    "Cloud",
    "Star",
    "Crystal",
    "Garden",
    "Ocean",
    "Falcon",
    "Wizard",
    "Aurora",
    "Badger",
    "Comet",
    "Dryad",
    "Eagle",
    "Fox",
    "Griffin",
    "Harbor",
    "Island",
    "Jaguar",
    "Knight",
    "Lion",
    "Mermaid",
    "Nebula",
    "Owl",
    "Panther",
    "Quasar",
    "Raven",
    "Serpent",
    "Tempest",
    "Unicorn",
    "Valley",
    "Wolf",
    "Sphinx",
    "Yeti",
    "Zenith",
    "Archer",
    "Beacon",
    "Cascade",
    "Dreamer",
    "Echo",
    "Flame",
    "Glacier",
    "Horizon",
    "Ivy",
]


def generate_memorable_name() -> str:
    """
    Generates a memorable two-word name combining a random adjective and noun.

    Returns:
        str: A memorable name in the format "Adjective Noun"

    Example:
        >>> generate_memorable_name()
        'Cosmic Dragon'
    """
    adjective = choice(ADJECTIVES)
    noun = choice(NOUNS)

    return f"{adjective} {noun}"
