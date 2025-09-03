import uuid


def string_to_uuid(s: str) -> uuid.UUID:
    """
    Derive a UUID from a string.
    """
    namespace_uuid = uuid.NAMESPACE_DNS
    uuid_from_name_sha1 = uuid.uuid5(namespace_uuid, s)
    return uuid_from_name_sha1
