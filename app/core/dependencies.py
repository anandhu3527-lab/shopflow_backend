from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

from app.models.user import User
from app.models.tenant import Tenant
from app.models.role import Role
from app.models.user_role import UserRole


# ============================================================
# HTTP BEARER SECURITY
# ============================================================

security = HTTPBearer()


# ============================================================
# GET CURRENT AUTHENTICATED USER
# ============================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify JWT and load the authenticated user's complete context.

    Returns:
        {
            "user_id": UUID,
            "tenant_id": UUID,
            "role_id": UUID,
            "user": User,
            "tenant": Tenant,
            "role": Role
        }

    Security rules:
    - JWT must be valid.
    - User must exist.
    - User must belong to the tenant in the JWT.
    - User must be ACTIVE.
    - Tenant must exist.
    - Tenant must be ACTIVE.
    - User must actually have the role from the JWT.
    """

    # ========================================================
    # 1. GET TOKEN
    # ========================================================

    token = credentials.credentials

    # ========================================================
    # 2. VERIFY JWT
    # ========================================================

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # ========================================================
    # 3. EXTRACT JWT CLAIMS
    # ========================================================

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    role_id = payload.get("role_id")

    if not user_id or not tenant_id or not role_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # ========================================================
    # 4. CONVERT IDS TO UUID
    # ========================================================

    try:
        user_uuid = UUID(str(user_id))
        tenant_uuid = UUID(str(tenant_id))
        role_uuid = UUID(str(role_id))

    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # ========================================================
    # 5. GET USER
    # ========================================================

    result = await db.execute(
        select(User).where(
            User.id == user_uuid,
            User.tenant_id == tenant_uuid,
        )
    )

    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # ========================================================
    # 6. CHECK USER STATUS
    # ========================================================

    if user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # ========================================================
    # 7. GET TENANT
    # ========================================================

    result = await db.execute(
        select(Tenant).where(
            Tenant.id == tenant_uuid
        )
    )

    tenant = result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Shop not found",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # ========================================================
    # 8. CHECK TENANT STATUS
    # ========================================================

    if tenant.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shop account is inactive",
        )

    # ========================================================
    # 9. GET USER ROLE
    # ========================================================

    result = await db.execute(
        select(Role)
        .join(
            UserRole,
            UserRole.role_id == Role.id
        )
        .where(
            UserRole.user_id == user_uuid,
            UserRole.role_id == role_uuid,
        )
    )

    role = result.scalar_one_or_none()

    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User role not found",
        )

    # ========================================================
    # 10. RETURN COMPLETE AUTHENTICATED CONTEXT
    # ========================================================

    return {
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "role_id": role.id,

        "user": user,
        "tenant": tenant,
        "role": role,
    }


# ============================================================
# AUTHORIZATION DEPENDENCY
# ============================================================

def require_roles(allowed_roles: list[str]):
    """
    Dependency to enforce role-based access control.
    """
    def role_checker(current_user: dict = Depends(get_current_user)):
        role_name = current_user["role"].name.upper()
        if role_name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of: {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker