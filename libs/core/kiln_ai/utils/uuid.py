import uuid

KILN_UUID_NAMESPACE = uuid.NAMESPACE_DNS


def string_to_uuid(s: str) -> uuid.UUID:
    """Return a deterministic UUIDv5 for the input string (namespaced; not for security)."""
    return uuid.uuid5(KILN_UUID_NAMESPACE, s)
