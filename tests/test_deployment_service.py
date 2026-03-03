import pytest

from app.schemas.deploy import DeployRequest
from app.schemas.common import EntityType, QuotaProfile, TargetEnvironment


@pytest.mark.asyncio
async def test_create_deployment(deployment_service):
    request = DeployRequest(
        entity_name="test-agent",
        entity_type=EntityType.AGENT,
        chart_name="ai-agent-chart",
        chart_version="1.0.0",
        artifactory_path="docker-local/test-agent",
        owner_username="jdoe",
        groups=["devs"],
        target_environment=TargetEnvironment.DEV,
        ttl_days=7,
        quota_profile=QuotaProfile.STANDARD,
    )

    response = await deployment_service.create_deployment(request)

    assert response.status == "success"
    assert response.namespace == "agent-jdoe-dev"
    assert "test-agent.agent-jdoe-dev.svc.cluster.local" in response.connection_url
    assert response.deployment_id  # UUID should be set


@pytest.mark.asyncio
async def test_list_deployments(deployment_service):
    deployments = await deployment_service.list_deployments(owner="testuser")
    assert len(deployments) >= 1
    assert deployments[0].entity_name == "test-entity"


@pytest.mark.asyncio
async def test_delete_deployment(deployment_service):
    # Should not raise
    await deployment_service.delete_deployment("test-entity-dev")
