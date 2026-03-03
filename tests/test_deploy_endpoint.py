def test_deploy_success(client):
    payload = {
        "entity_name": "data-analysis-agent",
        "entity_type": "agent",
        "chart_name": "ai-agent-chart",
        "chart_version": "1.0.0",
        "artifactory_path": "docker-local/data-analysis-agent",
        "owner_username": "jdoe",
        "groups": ["data_scientists", "developers"],
        "target_environment": "dev",
        "ttl_days": 10,
        "quota_profile": "standard",
    }
    resp = client.post("/api/infra/deploy", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "success"
    assert data["namespace"] == "agent-jdoe-dev"
    assert "deployment_id" in data
    assert "svc.cluster.local" in data["connection_url"]
    assert data["message"] == "Deployment triggered successfully"


def test_deploy_mcp_server(client):
    payload = {
        "entity_name": "bitbucket-mcp",
        "entity_type": "mcp_server",
        "chart_name": "mcp-server-chart",
        "chart_version": "2.0.0",
        "artifactory_path": "docker-local/mcp-server-bitbucket",
        "owner_username": "jdoe",
        "groups": [],
        "target_environment": "staging",
        "ttl_days": 30,
        "quota_profile": "large",
    }
    resp = client.post("/api/infra/deploy", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert data["namespace"] == "mcp-server-jdoe-staging"


def test_deploy_invalid_entity_name(client):
    payload = {
        "entity_name": "INVALID_NAME",
        "entity_type": "agent",
        "chart_name": "chart",
        "chart_version": "1.0.0",
        "artifactory_path": "path/to/image",
        "owner_username": "jdoe",
        "target_environment": "dev",
    }
    resp = client.post("/api/infra/deploy", json=payload)
    assert resp.status_code == 422


def test_deploy_invalid_environment(client):
    payload = {
        "entity_name": "test-agent",
        "entity_type": "agent",
        "chart_name": "chart",
        "chart_version": "1.0.0",
        "artifactory_path": "path/to/image",
        "owner_username": "jdoe",
        "target_environment": "invalid",
    }
    resp = client.post("/api/infra/deploy", json=payload)
    assert resp.status_code == 422


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_readiness(client):
    resp = client.get("/readiness")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
