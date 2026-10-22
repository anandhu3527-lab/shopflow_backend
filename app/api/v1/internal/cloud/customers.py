from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.internal.cloud.auth import verify_cloud_service_token
from app.api.v1.internal.cloud.schemas import (
    CloudCustomerListItem,
    CloudCustomerListResponse,
    PaginatedMeta,
)
from app.models.customer import Customer
from app.models.kadan_account import KadanAccount
from app.models.tenant import Tenant

router = APIRouter(
    prefix="/shops/{tenant_id}/customers",
    tags=["Cloud Internal - Customer Management"],
    dependencies=[Depends(verify_cloud_service_token)],
)


@router.get("", response_model=CloudCustomerListResponse)
async def list_shop_customers(
    tenant_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    List customers scoped to the shop with bounded pagination and optional search.
    """
    tenant_res = await db.execute(select(Tenant.id).where(Tenant.id == tenant_id))
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    count_query = select(func.count(Customer.id)).where(Customer.tenant_id == tenant_id)

    query = (
        select(Customer, KadanAccount.outstanding_amount.label("kadan_balance"))
        .outerjoin(
            KadanAccount,
            (KadanAccount.customer_id == Customer.id) & (KadanAccount.tenant_id == tenant_id),
        )
        .where(Customer.tenant_id == tenant_id)
    )

    if search:
        search_pattern = f"%{search.strip()}%"
        search_cond = or_(
            Customer.name.ilike(search_pattern),
            Customer.phone.ilike(search_pattern),
        )
        query = query.where(search_cond)
        count_query = count_query.where(search_cond)

    query = (
        query.order_by(Customer.created_at.desc(), Customer.id.desc())
        .limit(limit)
        .offset(offset)
    )

    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    results = await db.execute(query)
    rows = results.all()

    customer_items = [
        CloudCustomerListItem(
            id=c.id,
            tenant_id=c.tenant_id,
            name=c.name,
            phone=c.phone,
            status=c.status,
            created_at=c.created_at,
            updated_at=c.updated_at,
            kadan_balance=k_bal,
        )
        for c, k_bal in rows
    ]

    return CloudCustomerListResponse(
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        customers=customer_items,
    )
