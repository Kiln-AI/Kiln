import uuid

# do not change this, or this will break backwards compatibility with existing UUIDs
KILN_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "kiln.tech")


def string_to_uuid(s: str) -> uuid.UUID:
    """Return a deterministic UUIDv5 for the input string."""
    return uuid.uuid5(KILN_UUID_NAMESPACE, s)
