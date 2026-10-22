from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.tenant import TenantMeResponse, TenantUpdateRequest
from app.services.tenant_service import tenant_service

router = APIRouter(
    prefix="/tenants",
    tags=["Tenants"],
)


@router.get(
    "/me",
    response_model=TenantMeResponse,
)
async def get_tenant_me(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get complete details of the authenticated user's shop and its employees.
    OWNER ONLY.
    """
    return await tenant_service.get_tenant_me(
        db=db,
        current_user=current_user,
    )


@router.patch(
    "/me",
)
async def update_tenant_me(
    update_data: TenantUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update the authenticated user's shop details.
    OWNER ONLY.
    """
    return await tenant_service.update_tenant(
        db=db,
        current_user=current_user,
        update_data=update_data,
    )

