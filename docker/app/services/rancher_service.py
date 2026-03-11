import asyncio
import ssl

import httpx
import structlog
from ldap3 import Server, Connection, SIMPLE, SUBTREE

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
            user=f"{self.settings.ldap_username}@nsogroup.com",
            password=self.settings.ldap_password,
            authentication=SIMPLE,
            auto_bind=True,
        )
        return conn

    def _get_user_info_from_ldap(self, username: str) -> tuple[str, list[str]]:
        """Query AD for the user's DN and group memberships (filtered to Kubernetes OU).

        Returns (user_dn, groups) where groups are formatted as Rancher AD group principals.
        """
        conn = self._get_ldap_connection()
        try:
            # Find the user by sAMAccountName
            conn.search(
                self.settings.ldap_base_dn,
                f"(&(sAMAccountName={username})(objectClass=User))",
                attributes=["memberOf", "distinguishedName"],
                search_scope=SUBTREE,
            )
            if not conn.entries:
                raise ValueError(f"LDAP user not found: {username}")

            user_dn = str(conn.entries[0].distinguishedName)
            member_of = conn.entries[0].memberOf.values if conn.entries[0].memberOf else []

            # Filter to Kubernetes OU groups and format as Rancher AD group principals
            groups = []
            for group_dn in member_of:
                if KUBERNETES_OU_MARKER in group_dn:
                    groups.append(f"activedirectory_group://{group_dn}")

            logger.info("ldap_user_resolved", username=username, user_dn=user_dn, groups=groups)
            return user_dn, groups
        finally:
            conn.unbind()

    async def get_user_id(self, username: str, user_dn: str) -> str:
        """Resolve a Rancher user ID using the LDAP DN.

        Extracts the CN from the DN and searches Rancher by display name.
        Falls back to username field for local users.
        """
        # Try by username field first (works for local users like "permy")
        resp = await self._client.get("/v3/users", params={"username": username})
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            return data[0]["id"]

        # For AD users, extract CN from DN and search by name (display name)
        # DN looks like: CN=Roei Zaidler,OU=MEP Acquisition,...
        cn = user_dn.split(",")[0].removeprefix("CN=")
        resp = await self._client.get("/v3/users", params={"name": cn})
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            logger.info("rancher_user_found_by_cn", username=username, user_id=data[0]["id"], cn=cn)
            return data[0]["id"]

        raise ValueError(f"Rancher user not found: {username} (CN: {cn})")

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

    @staticmethod
    def extract_project_id(group_principal: str) -> str | None:
        """Extract Rancher project ID from an AD group principal.

        Group principal format: activedirectory_group://CN=kubernetes-qa-androidiphone-group,OU=...
        Group CN format: kubernetes-<project>-...
        Returns: p-<project> (e.g. p-qa, p-android)
        """
        # Extract CN from the principal
        prefix = "activedirectory_group://CN="
        if not group_principal.startswith(prefix):
            return None
        cn = group_principal[len(prefix):].split(",")[0]  # e.g. kubernetes-qa-androidiphone-group
        parts = cn.split("-")
        if len(parts) >= 2 and parts[0].lower() == "kubernetes":
            return f"p-{parts[1]}"
        return None

    async def resolve_user(self, username: str) -> tuple[str, list[str], str | None]:
        """Resolve username to (rancher_user_id, ad_groups, project_id) for impersonation.

        1. Get user's DN and AD groups from LDAP
        2. Get Rancher user ID by matching DN in principalIds
        3. Intersect AD groups with groups that have project bindings on this cluster
        4. Extract project ID from effective groups
        5. Return (user_id, effective_groups, project_id)
        """
        # Get user DN and groups from LDAP first (needed for Rancher lookup)
        user_dn, user_groups = await asyncio.to_thread(self._get_user_info_from_ldap, username)

        # Now run Rancher lookups in parallel
        user_id, cluster_groups = await asyncio.gather(
            self.get_user_id(username, user_dn),
            self.get_cluster_groups(),
        )

        # Intersect: only groups the user is in AND that have cluster/project bindings
        effective_groups = sorted(set(user_groups) & cluster_groups)

        # Extract project ID from the first effective group
        project_id = None
        for group in effective_groups:
            project_id = self.extract_project_id(group)
            if project_id:
                break

        logger.info(
            "resolved_user",
            username=username,
            user_id=user_id,
            user_dn=user_dn,
            user_ad_groups=len(user_groups),
            cluster_groups=len(cluster_groups),
            effective_groups=effective_groups,
            project_id=project_id,
        )
        return user_id, effective_groups, project_id

    async def close(self):
        await self._client.aclose()
