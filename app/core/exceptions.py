class DeploymentError(Exception):
    def __init__(self, deployment_id: str, message: str):
        self.deployment_id = deployment_id
        self.message = message
        super().__init__(f"Deployment {deployment_id} failed: {message}")


class ArgocdError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class BackendNotAvailableError(Exception):
    pass
