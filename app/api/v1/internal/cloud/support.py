from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.internal.cloud.auth import verify_cloud_service_token
from app.api.v1.internal.cloud.schemas import CloudSupportResponse
from app.models.tenant import Tenant

router = APIRouter(
    prefix="/shops/{tenant_id}/support",
    tags=["Cloud Internal - Support Management"],
    dependencies=[Depends(verify_cloud_service_token)],
)


@router.get("", response_model=CloudSupportResponse)
async def get_shop_support_status(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Truthful support ticket inquiry for the shop.
    Clearly reports that an in-database ticketing system is not currently implemented in ShopFlow.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    return CloudSupportResponse(
        supported=False,
        message=(
            "ShopFlow does not currently have an in-database customer support ticket model. "
            "Customer support workflows are managed through external help desk integrations or direct communication."
        ),
        tenant_id=tenant_id,
        tickets=[],
    )
