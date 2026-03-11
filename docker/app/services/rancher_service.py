import asyncio
import ssl

import httpx
import structlog
from ldap3 import Server, Connection, NTLM, SUBTREE

from app.config import Settings

logger = structlog.get_logger()

KUBERNETES_OU_MARKER = "OU=Kubernetes"


class RancherService:
    """Resolve Rancher usernames to user IDs and AD group memberships."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.cluster_id = settings.rancher_cluster_id

        # Rancher HTTP client
        ssl_context: ssl.SSLContext | bool = True
        if settings.ca_bundle_path:
            ssl_context = ssl.create_default_context(cafile=settings.ca_bundle_path)
        self._client = httpx.AsyncClient(
            base_url=settings.rancher_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.rancher_token}",
                "Content-Type": "application/json",
            },
            verify=ssl_context,
            timeout=30.0,
        )

    def _get_ldap_connection(self) -> Connection:
        server = Server(self.settings.ldap_server)
        conn = Connection(
            server,
            user=f"nsogroup\\{self.settings.ldap_username}",
            password=self.settings.ldap_password,
            authentication=NTLM,
            auto_bind=True,
        )
        return conn

    def _get_user_groups_from_ldap(self, username: str) -> list[str]:
        """Query AD for the user's group memberships, filtered to Kubernetes OU."""
        conn = self._get_ldap_connection()
        try:
            # Find the user by sAMAccountName
            conn.search(
                self.settings.ldap_base_dn,
                f"(&(sAMAccountName={username})(objectClass=User))",
                attributes=["memberOf"],
                search_scope=SUBTREE,
            )
            if not conn.entries:
                raise ValueError(f"LDAP user not found: {username}")

            member_of = conn.entries[0].memberOf.values if conn.entries[0].memberOf else []

            # Filter to Kubernetes OU groups and format as Rancher AD group principals
            groups = []
            for group_dn in member_of:
                if KUBERNETES_OU_MARKER in group_dn:
                    groups.append(f"activedirectory_group://{group_dn}")

            logger.info("ldap_groups_resolved", username=username, groups=groups)
            return groups
        finally:
            conn.unbind()

    async def get_user_id(self, username: str) -> str:
        """Resolve a Rancher username to its internal user ID (e.g. u-xxxxx)."""
        resp = await self._client.get("/v3/users", params={"username": username})
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            raise ValueError(f"Rancher user not found: {username}")
        return data[0]["id"]

    async def get_cluster_groups(self) -> set[str]:
        """Get all Kubernetes OU AD groups that have project bindings on this cluster."""
        groups: set[str] = set()
        resp = await self._client.get(
            "/v3/projectroletemplatebindings",
            params={"clusterId": self.cluster_id},
        )
        resp.raise_for_status()
        for binding in resp.json().get("data", []):
            gid = binding.get("groupPrincipalId")
            if gid and KUBERNETES_OU_MARKER in gid:
                groups.add(gid)
        return groups

    async def resolve_user(self, username: str) -> tuple[str, list[str]]:
        """Resolve username to (rancher_user_id, ad_groups) for impersonation.

        1. Get Rancher user ID from Rancher API
        2. Get user's AD groups from LDAP (filtered to Kubernetes OU)
        3. Intersect with groups that have project bindings on this cluster
        4. Return only the groups the user actually belongs to AND that have permissions
        """
        # Run Rancher API calls and LDAP query in parallel
        user_id_task = self.get_user_id(username)
        cluster_groups_task = self.get_cluster_groups()
        ldap_groups_task = asyncio.to_thread(self._get_user_groups_from_ldap, username)

        user_id, cluster_groups, user_groups = await asyncio.gather(
            user_id_task, cluster_groups_task, ldap_groups_task
        )

        # Intersect: only groups the user is in AND that have cluster/project bindings
        effective_groups = sorted(set(user_groups) & cluster_groups)

        logger.info(
            "resolved_user",
            username=username,
            user_id=user_id,
            user_ad_groups=len(user_groups),
            cluster_groups=len(cluster_groups),
            effective_groups=effective_groups,
        )
        return user_id, effective_groups

    async def close(self):
        await self._client.aclose()
