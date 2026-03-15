def build_namespace(group: str, entity_type: str, entity_name: str, environment: str) -> str:
    """Build a deterministic namespace: {group}-{type}-{entity_name}-{env}.

    Example: qa-agent-my-test-app-dev
    """
    entity_type_normalized = entity_type.replace("_", "-")
    ns = f"{group}-{entity_type_normalized}-{entity_name}-{environment}"
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
