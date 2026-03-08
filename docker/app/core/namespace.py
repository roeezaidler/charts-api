def build_namespace(entity_type: str, owner_username: str, environment: str) -> str:
    """Build a deterministic namespace: {entity_type}-{owner}-{env}.

    Multiple deployments by the same user/type/env share a namespace.
    """
    entity_type_normalized = entity_type.replace("_", "-")
    ns = f"{entity_type_normalized}-{owner_username}-{environment}"
    if len(ns) > 63:
        ns = ns[:63].rstrip("-")
    return ns


def build_release_name(entity_name: str, environment: str) -> str:
    """Build a deterministic release/application name: {entity_name}-{env}.

    Deterministic so that re-deploying the same entity upgrades in place.
    """
    release = f"{entity_name}-{environment}"
    if len(release) > 53:
        release = release[:53].rstrip("-")
    return release
