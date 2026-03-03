from app.core.quota_profiles import build_values_overrides, values_to_yaml, QUOTA_PROFILES
from app.core.namespace import build_namespace, build_release_name


def test_quota_profiles_exist():
    assert "small" in QUOTA_PROFILES
    assert "standard" in QUOTA_PROFILES
    assert "large" in QUOTA_PROFILES


def test_build_values_standard():
    values = build_values_overrides(
        entity_name="my-agent",
        entity_type="agent",
        artifactory_path="docker-local/my-agent",
        quota_profile="standard",
        target_environment="dev",
        owner_username="jdoe",
        groups=["devs"],
    )

    assert values["image"]["repository"] == "docker-local/my-agent"
    assert values["resources"]["requests"]["cpu"] == "250m"
    assert values["resources"]["limits"]["memory"] == "1Gi"
    assert values["replicaCount"] == 1


def test_build_values_large():
    values = build_values_overrides(
        entity_name="big-agent",
        entity_type="agent",
        artifactory_path="docker-local/big-agent",
        quota_profile="large",
        target_environment="prod",
        owner_username="admin",
        groups=[],
    )
    assert values["replicaCount"] == 2
    assert values["resources"]["limits"]["cpu"] == "2000m"


def test_values_to_yaml():
    values = {"image": {"repository": "test"}, "replicaCount": 1}
    yaml_str = values_to_yaml(values)
    assert "repository: test" in yaml_str
    assert "replicaCount: 1" in yaml_str


def test_build_namespace():
    assert build_namespace("agent", "jdoe", "dev") == "agent-jdoe-dev"
    assert build_namespace("mcp_server", "jdoe", "prod") == "mcp-server-jdoe-prod"


def test_build_namespace_long():
    long_user = "a" * 60
    ns = build_namespace("agent", long_user, "dev")
    assert len(ns) <= 63


def test_build_release_name():
    assert build_release_name("data-analysis-agent", "dev") == "data-analysis-agent-dev"


def test_build_release_name_long():
    long_name = "a" * 50
    release = build_release_name(long_name, "dev")
    assert len(release) <= 53
