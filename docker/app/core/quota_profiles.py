import yaml

QUOTA_PROFILES: dict[str, dict] = {
    "small": {
        "resources": {
            "requests": {"cpu": "100m", "memory": "128Mi"},
            "limits": {"cpu": "500m", "memory": "512Mi"},
        },
        "replicaCount": 1,
    },
    "standard": {
        "resources": {
            "requests": {"cpu": "250m", "memory": "256Mi"},
            "limits": {"cpu": "1000m", "memory": "1Gi"},
        },
        "replicaCount": 1,
    },
    "large": {
        "resources": {
            "requests": {"cpu": "500m", "memory": "512Mi"},
            "limits": {"cpu": "2000m", "memory": "4Gi"},
        },
        "replicaCount": 2,
    },
}


def build_values_overrides(
    entity_name: str,
    entity_type: str,
    artifactory_path: str,
    quota_profile: str,
    target_environment: str,
    owner_username: str,
    groups: list[str],
    service_type: str = "ClusterIP",
    service_port: int = 8080,
) -> dict:
    """Build the Helm values override dict from request params + quota profile."""
    profile = QUOTA_PROFILES[quota_profile]

    values = {
        "image": {
            "repository": artifactory_path,
            "tag": "latest",
            "pullPolicy": "Always",
        },
        "resources": profile["resources"],
        "replicaCount": profile["replicaCount"],
        "service": {
            "type": service_type,
            "port": service_port,
        },
        "env": {
            "ENTITY_NAME": entity_name,
            "ENTITY_TYPE": entity_type,
            "ENVIRONMENT": target_environment,
        },
    }
    return values


def values_to_yaml(values: dict) -> str:
    """Serialize values dict to YAML string for Helm --values file."""
    return yaml.dump(values, default_flow_style=False)


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override dict into base dict. Override wins on conflicts."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
