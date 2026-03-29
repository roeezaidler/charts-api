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
        key_alias = f"agent-{project}-{entity_name}"

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
