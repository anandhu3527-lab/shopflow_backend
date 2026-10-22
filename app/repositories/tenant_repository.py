import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole


class TenantRepository:
    """
    Repository for tenant-related operations.
    """

    async def get_tenant_users_with_roles(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Sequence[tuple[User, Role]]:
        """
        Fetch all users belonging to a tenant along with their roles.
        This performs an explicit join to avoid N+1 queries.
        """
        result = await db.execute(
            select(User, Role)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(User.tenant_id == tenant_id)
        )
        return result.all()


tenant_repository = TenantRepository()
