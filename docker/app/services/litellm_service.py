import uuid

import httpx
import structlog

logger = structlog.get_logger()


class LiteLLMService:
    def __init__(self, litellm_url: str, master_key: str, key_duration_days: int = 30):
        self.litellm_url = litellm_url.rstrip("/")
        self.master_key = master_key
        self.key_duration_days = key_duration_days

    async def generate_key(self, project: str, entity_name: str) -> dict:
        """Generate a LiteLLM API key for an agent deployment."""
        suffix = uuid.uuid4().hex[:6]
        key_alias = f"agent-{project}-{entity_name}-{suffix}"

        payload = {
            "key_alias": key_alias,
        }

        headers = {"Authorization": f"Bearer {self.master_key}"}

        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{self.litellm_url}/key/generate",
                json=payload,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        logger.info(
            "litellm_key_generated",
            key_alias=key_alias,
            key_name=data.get("key_name"),
        )

        return {"key": data["key"], "key_alias": key_alias}

    async def delete_keys(self, project: str, entity_name: str) -> int:
        """Delete all LiteLLM API keys matching agent-{project}-{entity_name}-*."""
        prefix = f"agent-{project}-{entity_name}-"
        headers = {"Authorization": f"Bearer {self.master_key}"}
        deleted = 0

        async with httpx.AsyncClient(verify=False) as client:
            # List all keys
            resp = await client.get(
                f"{self.litellm_url}/key/list",
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            keys = resp.json().get("keys", [])

            for key_info in keys:
                alias = key_info.get("key_alias") or ""
                if alias.startswith(prefix):
                    token = key_info.get("token")
                    if token:
                        del_resp = await client.post(
                            f"{self.litellm_url}/key/delete",
                            json={"keys": [token]},
                            headers=headers,
                            timeout=10,
                        )
                        if del_resp.status_code == 200:
                            deleted += 1
                            logger.info("litellm_key_deleted", key_alias=alias)

        return deleted
