import secrets
from fastapi import Header, HTTPException, status
from app.core.config import settings


async def verify_cloud_service_token(
    x_cryvex_cloud_service_token: str | None = Header(
        default=None,
        alias="X-Cryvex-Cloud-Service-Token",
        description="Dedicated internal service authentication token for CRYVEX Cloud",
    ),
) -> str:
    """
    Authenticate incoming server-to-server requests from CRYVEX Cloud backend.
    
    Security rules:
    - Dedicated service token check only.
    - Constant-time comparison using secrets.compare_digest.
    - Token is never logged or returned.
    - Fails closed if server-side CLOUD_INTERNAL_SERVICE_TOKEN is missing or empty.
    - Rejects missing token with 401 Unauthorized.
    - Rejects invalid token with 403 Forbidden.
    """
    expected_token = settings.CLOUD_INTERNAL_SERVICE_TOKEN
    
    # Fail closed if the server is not configured with a valid token
    if not expected_token or not expected_token.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cloud internal service authentication is not configured",
        )
    
    if not x_cryvex_cloud_service_token or not x_cryvex_cloud_service_token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required service authentication header: X-Cryvex-Cloud-Service-Token",
        )
    
    # Constant-time comparison to protect against timing attacks
    if not secrets.compare_digest(
        x_cryvex_cloud_service_token.strip().encode("utf-8"),
        expected_token.strip().encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal service token",
        )
    
    return "CRYVEX_CLOUD_SERVICE"
